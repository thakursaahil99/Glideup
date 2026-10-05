"""Grade framework-test answers.

MCQs are exact. Reviews, viva answers and projects are judged item by item (planted issues,
key points, requirements) by the LLM; the score is computed here from those judgements and
the item weights, never taken from the model. Project requirements with a pattern are also
checked statically: a missing pattern caps that item at 0 whatever the model says, and a
present one guarantees at least half credit.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.llm import prompt_store
from app.llm.factory import MOCK_HANDLERS, get_gateway
from app.llm.routing import Task
from app.llm.types import CallContext, CompletionRequest

SECTION_WEIGHTS = {"mcq": 0.3, "review": 0.2, "viva": 0.2, "project": 0.3}
CREDIT = {"yes": 1.0, "partial": 0.5, "no": 0.0}
LEVELS = ((80, "expert"), (60, "advanced"), (40, "intermediate"), (0, "beginner"))
MAX_ANSWER = 12000


def level_for(score: int) -> str:
    return next(name for floor, name in LEVELS if score >= floor)


class Judgement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    met: Literal["yes", "partial", "no"] = "no"
    note: str | None = Field(default=None, max_length=400)

    @field_validator("met", mode="before")
    @classmethod
    def _met(cls, value: object) -> str:
        text = str(value or "").lower()
        return (
            "yes" if text in ("yes", "true", "met", "1") else "partial" if "part" in text else "no"
        )

    @field_validator("note", mode="before")
    @classmethod
    def _clip(cls, value: object) -> object:
        return value[:400] if isinstance(value, str) else value


class GradeDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[Judgement] = Field(default_factory=list, max_length=20)
    feedback: str = Field(default="", max_length=1000)

    @field_validator("feedback", mode="before")
    @classmethod
    def _clip(cls, value: object) -> object:
        return value[:1000] if isinstance(value, str) else value


@dataclass
class QuestionGrade:
    score: float  # 0-1
    feedback: str
    items: list[dict[str, Any]] = field(default_factory=list)


def grade_mcq(content: dict[str, Any], answer: Any) -> QuestionGrade:
    correct = isinstance(answer, int) and answer == content["answer"]
    return QuestionGrade(
        1.0 if correct else 0.0,
        content.get("explanation") or "",
        [{"key": "answer", "met": "yes" if correct else "no", "correct": content["answer"]}],
    )


def _rubric(question_type: str, content: dict[str, Any]) -> list[dict[str, Any]]:
    if question_type == "review":
        return list(content["issues"])
    if question_type == "project":
        return list(content["requirements"])
    return [
        {"key": f"p{i}", "description": text, "weight": 1}
        for i, text in enumerate(content["key_points"])
    ]


def score_items(
    question_type: str, rubric: list[dict[str, Any]], draft: GradeDraft, answer: str
) -> tuple[float, list[dict[str, Any]]]:
    judged = {j.key: j for j in draft.items}
    total = sum(item.get("weight", 1) for item in rubric) or 1
    earned = 0.0
    items = []
    for item in rubric:
        judgement = judged.get(item["key"])
        credit = CREDIT[judgement.met] if judgement else 0.0
        pattern = item.get("pattern") if question_type == "project" else None
        if pattern:
            present = re.search(pattern, answer) is not None
            credit = max(credit, 0.5) if present else 0.0
        earned += credit * item.get("weight", 1)
        items.append({"key": item["key"], "description": item["description"], "credit": credit,
                      "note": judgement.note if judgement else None})  # fmt: skip
    return round(earned / total, 3), items


async def grade_open(
    *,
    framework: str,
    question_type: str,
    statement: str,
    content: dict[str, Any],
    answer: str,
    user_id: object,
) -> QuestionGrade:
    answer = (answer or "").strip()[:MAX_ANSWER]
    rubric = _rubric(question_type, content)
    if not answer:
        unanswered = [
            {"key": r["key"], "description": r["description"], "credit": 0.0, "note": None}
            for r in rubric
        ]
        return QuestionGrade(0.0, "No answer was given.", unanswered)
    messages, version = await prompt_store.render(
        "framework_grade",
        framework=framework,
        question_type=question_type,
        statement=statement,
        code=content.get("code", "") if question_type == "review" else "",
        items=[{"key": r["key"], "description": r["description"]} for r in rubric],
        answer=answer,
    )
    draft, _ = await get_gateway().complete_json(
        Task.FRAMEWORK_GRADE, messages, GradeDraft,
        ctx=CallContext(user_id=user_id, prompt_version=version), max_tokens=1200,
    )  # fmt: skip
    score, items = score_items(question_type, rubric, draft, answer)
    return QuestionGrade(score, draft.feedback, items)


def combine(sections: dict[str, list[float]]) -> tuple[int, dict[str, int]]:
    """Section averages (0-100) and the weighted overall score over sections present."""
    averages = {k: round(100 * sum(v) / len(v)) for k, v in sections.items() if v}
    weight = sum(SECTION_WEIGHTS[k] for k in averages) or 1
    overall = round(sum(SECTION_WEIGHTS[k] * averages[k] for k in averages) / weight)
    return overall, averages


# ------------------------------------------------------------------ mock (tests, offline)

_ITEM = re.compile(r"^- (\w+): (.+)$", re.M)
_ANSWER = re.compile(r"<answer>\n?(.*?)\n?</answer>", re.S)


def _mock_grade(request: CompletionRequest) -> str:
    """Credits an item when its description's words appear in the answer."""
    system, user = request.messages[0].content, request.messages[-1].content
    answer = (m.group(1) if (m := _ANSWER.search(user)) else "").lower()
    items = []
    for key, description in _ITEM.findall(system):
        words = re.findall(r"[a-z]{4,}", description.lower())
        hits = sum(w in answer for w in words)
        met = "yes" if words and hits >= max(1, len(words) // 3) else "partial" if hits else "no"
        items.append({"key": key, "met": met, "note": ""})
    return json.dumps(
        {"items": items, "feedback": "Solid answer; cover every key point to score higher."}
    )


MOCK_HANDLERS[Task.FRAMEWORK_GRADE] = _mock_grade
