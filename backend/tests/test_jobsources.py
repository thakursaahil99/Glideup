"""Job source plugins, the polite HTTP client and normalisation (no network)."""

import json
from decimal import Decimal
from typing import Any

import httpx
import pytest

from app.db.models import ExperienceLevel, WorkMode
from app.jobsources.base import BoardTarget, FetchContext, Posting
from app.jobsources.geo import guess_country, location_terms
from app.jobsources.http import SourceHttpClient, SourceHttpError
from app.jobsources.normalize import (
    dedup_hash,
    detect_experience_level,
    detect_work_mode,
    html_to_text,
    normalize,
    sanitize_html,
)
from app.jobsources.plugins.ats import AshbyPlugin, GreenhousePlugin, LeverPlugin


class Sleeper:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def client_for(handler: Any, sleeper: Sleeper | None = None, rate: int = 6000) -> SourceHttpClient:
    return SourceHttpClient(
        rate_limit_per_minute=rate,
        base_delay=1.0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        sleep=sleeper or Sleeper(),
    )


# --- normalisation ---


def test_sanitizer_keeps_formatting_and_strips_active_content() -> None:
    dirty = (
        '<p onclick="steal()">Hi <strong>there</strong></p><script>alert(1)</script>'
        '<a href="javascript:evil()">x</a><a href="https://example.com">site</a>'
        '<img src=x onerror=alert(1)><iframe src="https://evil"></iframe>'
    )
    clean = sanitize_html(dirty)
    assert "<strong>there</strong>" in clean
    for bad in ("script", "onclick", "javascript:", "<img", "iframe", "onerror"):
        assert bad not in clean
    assert 'rel="noopener noreferrer nofollow"' in clean


def test_greenhouse_escaped_html_is_unescaped_then_sanitised() -> None:
    clean = sanitize_html(
        "&lt;p&gt;Build &lt;b&gt;APIs&lt;/b&gt;&lt;/p&gt;&lt;script&gt;x&lt;/script&gt;"
    )
    assert clean == "<p>Build <b>APIs</b></p>"
    assert html_to_text("<ul><li>Python</li><li>Go</li></ul><p>Done</p>") == "• Python\n• Go\nDone"


@pytest.mark.parametrize(
    ("posting", "text", "expected"),
    [
        (Posting("1", "Engineer", "Co", "https://x", workplace_hint="Hybrid"), "", WorkMode.HYBRID),
        (Posting("1", "Engineer", "Co", "https://x", remote_hint=True), "", WorkMode.REMOTE),
        (
            Posting("1", "Engineer", "Co", "https://x", location="Remote - India"),
            "",
            WorkMode.REMOTE,
        ),
        (Posting("1", "Engineer (Remote)", "Co", "https://x", location="US"), "", WorkMode.REMOTE),
        (
            Posting("1", "Engineer", "Co", "https://x", location="Pune"),
            "This is a hybrid role",
            WorkMode.HYBRID,
        ),
        (Posting("1", "Engineer", "Co", "https://x", workplace_hint="onsite"), "", WorkMode.ONSITE),
        (Posting("1", "Engineer", "Co", "https://x", location="Pune"), "", WorkMode.UNKNOWN),
    ],
)
def test_work_mode_detection(posting: Posting, text: str, expected: WorkMode) -> None:
    assert detect_work_mode(posting, text) == expected


@pytest.mark.parametrize(
    ("title", "level"),
    [
        ("Software Engineer Intern", ExperienceLevel.INTERNSHIP),
        ("International Sales Lead", ExperienceLevel.SENIOR),  # "intern" inside a word: no
        ("Staff Backend Engineer", ExperienceLevel.STAFF),
        ("Senior Engineering Manager", ExperienceLevel.MANAGER),
        ("Product Manager", ExperienceLevel.UNKNOWN),  # a role, not people management
        ("Senior Product Manager", ExperienceLevel.SENIOR),
        ("Director of Engineering", ExperienceLevel.MANAGER),
        ("Sr. Data Engineer", ExperienceLevel.SENIOR),
        ("Software Engineer II", ExperienceLevel.MID),
        ("New Grad Software Engineer", ExperienceLevel.ENTRY),
        ("Backend Engineer", ExperienceLevel.UNKNOWN),
    ],
)
def test_experience_level_detection(title: str, level: ExperienceLevel) -> None:
    assert detect_experience_level(title) == level


def test_dedup_hash_ignores_case_and_punctuation() -> None:
    assert dedup_hash("Senior Engineer, Payments", "Stripe", "Bengaluru, India") == dedup_hash(
        "senior engineer payments", "STRIPE", "Bengaluru India"
    )
    assert dedup_hash("Engineer", "Stripe", "Bengaluru") != dedup_hash("Engineer", "Stripe", "Pune")


def test_normalize_extracts_skills_and_hashes() -> None:
    job = normalize(
        Posting(
            "9",
            "  Senior   Python Engineer ",
            "Acme",
            "https://jobs.example.com/9",
            description_html="<p>We use FastAPI, PostgreSQL and k8s.</p>",
            location="Remote",
        )
    )
    assert job.title == "Senior Python Engineer"
    assert {"Python", "FastAPI", "PostgreSQL", "Kubernetes"} <= set(job.skills)
    assert job.work_mode == WorkMode.REMOTE
    assert job.experience_level == ExperienceLevel.SENIOR
    assert len(job.dedup_hash) == len(job.content_hash) == 64


def test_location_helpers() -> None:
    assert guess_country("Bengaluru-VTP, India") == "IN"
    assert guess_country("Bangalore - WF") == "IN"
    assert guess_country("San Francisco, CA") == "US"
    assert guess_country("Remote") is None
    assert "bengaluru" in location_terms("Bangalore - WF")
    assert "in" in location_terms("Bangalore - WF")


# --- HTTP client ---


async def test_retries_rate_limits_then_succeeds() -> None:
    responses = iter(
        [
            httpx.Response(429, headers={"retry-after": "7"}),
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    sleeper = Sleeper()
    http = client_for(lambda r: next(responses), sleeper)
    assert await http.get_json("https://api.example.com/x") == {"ok": True}
    assert http.requests_made == 3
    backoffs = [s for s in sleeper.calls if s >= 1]
    assert backoffs[0] == 7  # honours Retry-After
    assert 2 <= backoffs[1] <= 3  # exponential backoff with jitter


async def test_client_errors_are_not_retried() -> None:
    http = client_for(lambda r: httpx.Response(404))
    with pytest.raises(SourceHttpError) as excinfo:
        await http.get_json("https://api.example.com/missing")
    assert excinfo.value.status == 404
    assert http.requests_made == 1


async def test_gives_up_after_max_retries() -> None:
    http = client_for(lambda r: httpx.Response(500))
    with pytest.raises(SourceHttpError, match="HTTP 500"):
        await http.get_json("https://api.example.com/flaky")
    assert http.requests_made == 4


async def test_requests_are_spaced_to_the_rate_limit() -> None:
    sleeper = Sleeper()
    http = client_for(lambda r: httpx.Response(200, json=[]), sleeper, rate=60)  # 1 per second
    for _ in range(3):
        await http.get_json("https://api.example.com/x")
    assert len([s for s in sleeper.calls if 0.5 < s <= 2.0]) == 2


# --- ATS plugins (real response shapes, trimmed) ---

GREENHOUSE = {
    "jobs": [
        {
            "id": 101,
            "title": "Backend Engineer",
            "company_name": "Groww",
            "absolute_url": "https://job-boards.greenhouse.io/groww/jobs/101",
            "content": "&lt;p&gt;Python and Kafka&lt;/p&gt;",
            "location": {"name": "Bengaluru, India"},
            "departments": [{"name": "Engineering"}],
            "first_published": "2026-09-14T03:49:28-04:00",
        }
    ]
}
LEVER = [
    {
        "id": "abc",
        "text": "Senior Frontend Engineer",
        "hostedUrl": "https://jobs.lever.co/zeta/abc",
        "description": "<p>About us</p>",
        "lists": [{"text": "Requirements", "content": "<li>React</li><li>TypeScript</li>"}],
        "additional": "<p>Benefits</p>",
        "categories": {"location": "Bangalore - WF", "team": "Web", "commitment": "Full-time"},
        "workplaceType": "onsite",
        "country": "IN",
        "createdAt": 1788425813778,
        "salaryRange": {
            "min": 2000000,
            "max": 3000000,
            "currency": "INR",
            "interval": "per-year-salary",
        },
    }
]
ASHBY = {
    "jobs": [
        {
            "id": "a1",
            "title": "Staff Engineer",
            "location": "Europe",
            "isListed": True,
            "isRemote": True,
            "workplaceType": "Remote",
            "employmentType": "FullTime",
            "team": "Engineering",
            "jobUrl": "https://jobs.ashbyhq.com/linear/a1",
            "descriptionHtml": "<p>Rust and TypeScript</p>",
            "publishedAt": "2026-09-01T10:00:00.000+00:00",
            "address": {"postalAddress": {"addressCountry": "Germany"}},
            "compensation": {
                "summaryComponents": [
                    {
                        "compensationType": "Salary",
                        "interval": "1 YEAR",
                        "currencyCode": "EUR",
                        "minValue": 120000,
                        "maxValue": 160000,
                    }
                ]
            },
        },
        {"id": "hidden", "title": "Unlisted", "isListed": False, "jobUrl": "https://x"},
    ]
}


async def _collect(plugin: Any, payload: Any, token: str) -> list[Any]:
    def handle(request: httpx.Request) -> httpx.Response:
        if token in str(request.url):
            return httpx.Response(200, content=json.dumps(payload))
        return httpx.Response(404)

    ctx = FetchContext(
        client_for(handle),
        {},
        [BoardTarget("cid", "Company", token), BoardTarget("c2", "Gone", "missing")],
    )
    return [result async for result in plugin.fetch(ctx)]


async def test_greenhouse_plugin() -> None:
    ok, missing = await _collect(GreenhousePlugin(), GREENHOUSE, "groww")
    posting = ok.postings[0]
    assert (ok.scope, ok.company_id, ok.complete) == ("greenhouse:groww", "cid", True)
    # Our verified company name ("Company" in this fixture) wins over the board's free text.
    assert (posting.title, posting.company_name, posting.country) == (
        "Backend Engineer",
        "Company",
        "IN",
    )
    assert posting.department == "Engineering"
    assert posting.posted_at is not None
    assert posting.posted_at.year == 2026
    # A board that 404s is reported as incomplete, so its jobs are not marked stale.
    assert (missing.complete, missing.error) == (False, "HTTP 404")


async def test_lever_plugin_merges_sections_and_salary() -> None:
    ok, _ = await _collect(LeverPlugin(), LEVER, "zeta")
    posting = ok.postings[0]
    assert "<h3>Requirements</h3>" in posting.description_html
    assert "Benefits" in posting.description_html
    assert (posting.salary_min, posting.salary_currency, posting.salary_period) == (
        Decimal(2000000),
        "INR",
        "year",
    )
    assert (posting.workplace_hint, posting.employment_type, posting.country) == (
        "onsite",
        "Full-time",
        "IN",
    )


async def test_ashby_plugin_skips_unlisted_and_reads_compensation() -> None:
    ok, _ = await _collect(AshbyPlugin(), ASHBY, "linear")
    assert [p.external_id for p in ok.postings] == ["a1"]
    posting = ok.postings[0]
    assert (posting.salary_min, posting.salary_max, posting.salary_currency) == (
        Decimal(120000),
        Decimal(160000),
        "EUR",
    )
    assert (posting.country, posting.employment_type, posting.remote_hint) == (
        "DE",
        "Full-time",
        True,
    )


def test_job_skills_ignore_hr_boilerplate() -> None:
    job = normalize(
        Posting(
            "1",
            "Frontend Engineer",
            "Acme",
            "https://x.example.com/1",
            description_html=(
                "<p>Build UIs with React and TypeScript.</p>"
                "<p>We value great communication and leadership. We provide accessibility "
                "accommodations and take security seriously.</p>"
            ),
        )
    )
    assert set(job.skills) == {"React", "TypeScript"}


def test_normalizer_version_is_part_of_the_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.jobsources import normalize as module

    p = Posting("1", "Engineer", "Acme", "https://x.example.com/1")
    before = module.posting_hash(p)
    monkeypatch.setattr(module, "NORMALIZER_VERSION", "999")
    assert module.posting_hash(p) != before  # rule changes re-normalise every job once
