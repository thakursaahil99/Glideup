"""Shared normalisation: every source's postings end up in one clean, comparable shape."""

import hashlib
import html
import re
from dataclasses import dataclass

import nh3

from app.db.models import ExperienceLevel, WorkMode
from app.jobsources.base import Posting
from app.jobsources.geo import ParsedLocation, parse_location
from app.modules.resumes.skills import detect_skills

# Job descriptions are third-party HTML rendered in our pages: allow formatting only.
_ALLOWED_TAGS = {
    "p", "br", "ul", "ol", "li", "strong", "b", "em", "i", "u", "h2", "h3", "h4", "h5",
    "blockquote", "code", "pre", "a", "table", "thead", "tbody", "tr", "th", "td", "hr", "span",
}  # fmt: skip
_ALLOWED_ATTRIBUTES = {"a": {"href", "title"}}
MAX_DESCRIPTION_CHARS = 60_000


# Bump when normalisation rules change: every job is re-normalised on its next run.
NORMALIZER_VERSION = "5"  # 3-4: structured locations (country / state / city, remote scope)

# Job descriptions are full of boilerplate (HR and equal-opportunity text) that mentions
# "communication", "accessibility", "security"... Only concrete technical skills count.
JOB_SKILL_EXCLUDED_CATEGORIES = {"soft"}
JOB_SKILL_STOPLIST = {"Accessibility", "Security", "Agile", "Performance Optimization"}


def sanitize_html(raw: str) -> str:
    # Some APIs (Greenhouse) return HTML-escaped HTML.
    if "&lt;" in raw and "<" not in raw:
        raw = html.unescape(raw)
    return nh3.clean(
        raw[:MAX_DESCRIPTION_CHARS],
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer nofollow",
    )


def html_to_text(clean_html: str) -> str:
    text = re.sub(r"<(br|/p|/li|/h\d|/tr)\s*/?>", "\n", clean_html, flags=re.I)
    text = re.sub(r"<li[^>]*>", "• ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    return re.sub(r"\s*\n\s*", "\n", text).strip()


_REMOTE = re.compile(r"\b(remote|work from home|wfh|anywhere|distributed)\b", re.I)
_HYBRID = re.compile(r"\bhybrid\b", re.I)
_ONSITE = re.compile(r"\b(on-?site|in[- ]office)\b", re.I)


def detect_work_mode(posting: Posting, text: str) -> WorkMode:
    hint = (posting.workplace_hint or "").lower()
    if "hybrid" in hint:
        return WorkMode.HYBRID
    if "remote" in hint or posting.remote_hint is True:
        return WorkMode.REMOTE
    if "onsite" in hint or "on-site" in hint or "office" in hint:
        return WorkMode.ONSITE
    location = posting.location or ""
    if _HYBRID.search(location) or _HYBRID.search(posting.title):
        return WorkMode.HYBRID
    if _REMOTE.search(location) or _REMOTE.search(posting.title):
        return WorkMode.REMOTE
    if _ONSITE.search(location):
        return WorkMode.ONSITE
    if posting.remote_hint is False:
        return WorkMode.ONSITE
    head = text[:1500]  # only the top of the description: footers mention "remote" boilerplate
    if _HYBRID.search(head):
        return WorkMode.HYBRID
    return WorkMode.UNKNOWN


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(rf"\b({pattern})\b", re.I)


# First match wins, so the order matters (e.g. "Senior Engineering Manager" is a manager).
_LEVEL_RULES: list[tuple[re.Pattern[str], ExperienceLevel]] = [
    (_rx(r"intern|internship|co-?op|apprentice"), ExperienceLevel.INTERNSHIP),
    (_rx(r"principal|staff|distinguished|fellow|architect"), ExperienceLevel.STAFF),
    # People management only: "Product/Program/Account Manager" are roles, not seniority.
    (
        _rx(r"head of|director|vp|vice president|chief|engineering manager|manager,? engineering"),
        ExperienceLevel.MANAGER,
    ),
    (_rx(r"senior|sr\.?|lead|iii|iv"), ExperienceLevel.SENIOR),
    (_rx(r"junior|jr\.?|graduate|new grad|entry|associate|trainee|i"), ExperienceLevel.ENTRY),
    (_rx(r"ii|mid|intermediate"), ExperienceLevel.MID),
]


def detect_experience_level(title: str) -> ExperienceLevel:
    for pattern, level in _LEVEL_RULES:
        if pattern.search(title):
            return level
    return ExperienceLevel.UNKNOWN


def _norm(text: str | None) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", (text or "").lower()).split())


def dedup_hash(title: str, company: str, location: str | None) -> str:
    """Same role at the same company and place, regardless of which source listed it."""
    key = "|".join((_norm(title), _norm(company), _norm(location)))
    return hashlib.sha256(key.encode()).hexdigest()


def content_hash(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class NormalizedJob:
    posting: Posting
    title: str
    description_html: str
    description_text: str
    work_mode: WorkMode
    experience_level: ExperienceLevel
    skills: list[str]
    geo: ParsedLocation
    remote_scope: str | None
    dedup_hash: str
    content_hash: str


def normalize(posting: Posting) -> NormalizedJob:
    title = " ".join(posting.title.split())[:300]
    clean_html = sanitize_html(posting.description_html or "")
    text = html_to_text(clean_html)
    skills = [
        name
        for name, category in detect_skills(f"{title}\n{text}")
        if category not in JOB_SKILL_EXCLUDED_CATEGORIES and name not in JOB_SKILL_STOPLIST
    ]
    geo = parse_location(
        posting.location, country_hint=posting.country, region_hint=posting.region_hint
    )
    work_mode = detect_work_mode(posting, text)
    return NormalizedJob(
        posting=posting,
        title=title,
        description_html=clean_html,
        description_text=text,
        work_mode=work_mode,
        experience_level=detect_experience_level(title),
        skills=skills,
        geo=geo,
        remote_scope=remote_scope(work_mode, geo),
        dedup_hash=dedup_hash(title, posting.company_name, posting.location),
        content_hash=posting_hash(posting),
    )


def remote_scope(work_mode: WorkMode, geo: ParsedLocation) -> str | None:
    """ "country" = remote within the listed countries ("Remote - India");
    "worldwide" = remote with no country restriction ("Remote", "Anywhere", "Distributed")."""
    if work_mode != WorkMode.REMOTE:
        return None
    return "worldwide" if geo.worldwide or not geo.countries else "country"


def posting_hash(posting: Posting) -> str:
    """Hash of the RAW posting. Cheap to compute, so unchanged jobs (the vast majority on
    every scheduled run) skip sanitising and skill extraction entirely."""
    return content_hash(
        NORMALIZER_VERSION,
        posting.title,
        posting.location,
        posting.description_html,
        posting.apply_url,
        posting.salary_min,
        posting.salary_max,
        posting.employment_type,
        posting.workplace_hint,
        posting.remote_hint,
        posting.country,
        tuple(posting.region_hint or ()),
    )
