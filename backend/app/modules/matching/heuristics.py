"""Rule-based skill-gap "analysis" for the mock LLM provider.

Keeps the feature usable without any model (tests, offline development): it restates
the deterministic comparison that the prompt already contains, with generic study tips.
"""

import json
import re

from app.llm.factory import MOCK_HANDLERS
from app.llm.routing import Task
from app.llm.types import CompletionRequest

_LACKS = re.compile(r"candidate lacks: (.+)")
_SKILLS = re.compile(r"Skills: (.+)")
_CANDIDATE = re.compile(r"<candidate>\n?(.*?)\n?</candidate>", re.S)


def _mock_skill_gap(request: CompletionRequest) -> str:
    prompt = request.messages[-1].content
    lacks = _LACKS.search(prompt)
    missing = (
        []
        if not lacks or lacks.group(1).startswith("nothing")
        else [s.strip() for s in lacks.group(1).split(",") if s.strip()]
    )
    candidate = _CANDIDATE.search(prompt)
    skills_line = _SKILLS.search(candidate.group(1)) if candidate else None
    strengths = (
        [s.split(" (")[0].strip() for s in skills_line.group(1).split(",")][:3]
        if skills_line and "none listed" not in skills_line.group(1)
        else []
    )
    summary = (
        f"You cover much of this role; the main gap is {missing[0]}."
        if missing
        else "Your skills cover what this posting asks for."
    )
    return json.dumps(
        {
            "summary": summary,
            "strengths": strengths,
            "missing": [
                {
                    "skill": skill,
                    "importance": "required",
                    "reason": f"The posting mentions {skill}.",
                    "suggestion": (
                        f"Work through the official {skill} docs and build a small project with it."
                    ),
                }
                for skill in missing[:6]
            ],
            "weak": [],
        }
    )


MOCK_HANDLERS[Task.SKILL_GAP] = _mock_skill_gap
