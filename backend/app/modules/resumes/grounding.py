"""Grounding: keep only extracted facts that actually appear in the resume text.

Models hallucinate, and resumes can carry prompt-injection text ("ignore previous
instructions, my name is ..."). Checking facts against the source is cheap and doesn't
depend on the model resisting either. Skills are exempt: they are canonicalised
("JS" -> "JavaScript"), so they won't match the raw text literally.
"""

import re

from app.modules.resumes.heuristics import parse_resume_text
from app.modules.resumes.schemas import ParsedResume


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", text.lower()).split())


def _lazy_uniform_years(parsed: ParsedResume) -> bool:
    """Small models often stamp total experience onto every skill. Unknown beats invented."""
    years = {s.years for s in parsed.skills}
    return (
        len(parsed.skills) >= 5
        and len(years) == 1
        and None not in years
        and parsed.total_years_experience is not None
        and years == {parsed.total_years_experience}
    )


def ground(parsed: ParsedResume, source: str) -> ParsedResume:
    haystack = _norm(source)

    def present(value: str | None) -> bool:
        return bool(value) and _norm(value or "") in haystack

    full_name = parsed.full_name if present(parsed.full_name) else None
    if full_name is None:
        fallback = parse_resume_text(source).get("full_name")
        full_name = fallback if isinstance(fallback, str) else None

    links = [
        link
        for link in parsed.links
        if _norm(re.sub(r"^https?://(www\.)?", "", link).rstrip("/")) in haystack
    ]
    skills = parsed.skills
    if _lazy_uniform_years(parsed):
        skills = [s.model_copy(update={"years": None}) for s in skills]
    if len(skills) >= 5 and len({s.level for s in skills}) == 1:
        # Same level for every skill carries no signal (models default to "expert").
        skills = [s.model_copy(update={"level": None}) for s in skills]
    return parsed.model_copy(
        update={
            "full_name": full_name,
            "skills": skills,
            "experience": [job for job in parsed.experience if present(job.company)],
            "education": [e for e in parsed.education if present(e.institution)],
            "links": links,
        }
    )
