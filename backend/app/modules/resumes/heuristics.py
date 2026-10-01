"""Heuristic resume parser used by the mock LLM provider.

Not a replacement for a model — it finds known skills, an overall years-of-experience
figure, a name and links — but it keeps the whole pipeline usable with no LLM at all
(tests, CI, load tests, or a laptop without Ollama).
"""

import json
import re

from app.llm.factory import MOCK_HANDLERS
from app.llm.routing import Task
from app.llm.types import CompletionRequest
from app.modules.resumes.skills import detect_skills

_RESUME_BLOCK = re.compile(r"<resume>\n?(.*?)\n?</resume>", re.S)
_YEARS = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years|yrs)", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_LINK = re.compile(r"(?:https?://)?(?:www\.)?(?:github\.com|linkedin\.com/in)/[\w./-]+", re.I)


def parse_resume_text(text: str) -> dict[str, object]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    first = lines[0] if lines else ""
    looks_like_name = bool(first) and len(first.split()) <= 4 and not _EMAIL.search(first)
    years = [float(y) for y in _YEARS.findall(text)]
    return {
        "full_name": first if looks_like_name else None,
        "headline": lines[1][:200] if len(lines) > 1 and looks_like_name else None,
        "summary": None,
        "total_years_experience": max(years) if years else None,
        "location": None,
        "skills": [{"name": name, "category": category} for name, category in detect_skills(text)],
        "experience": [],
        "education": [],
        "certifications": [],
        "links": sorted(set(_LINK.findall(text))),
    }


def _mock_resume_parse(request: CompletionRequest) -> str:
    prompt = "\n".join(m.content for m in request.messages if m.role == "user")
    match = _RESUME_BLOCK.search(prompt)
    return json.dumps(parse_resume_text(match.group(1) if match else prompt))


MOCK_HANDLERS[Task.RESUME_PARSE] = _mock_resume_parse
