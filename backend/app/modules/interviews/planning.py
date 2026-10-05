"""Which questions an interview asks.

DSA, system design and behavioral rounds draw from the curated bank (`bank.json`; the
admin-managed question bank replaces it in Phase 6), preferring the chosen difficulty and
avoiding questions the user saw recently. Job-specific rounds are written by the LLM from
the posting and the user's background, with a deterministic plan as the fallback, so an
interview can always start.
"""

import json
import random
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

from app.db.models import Difficulty, Job
from app.llm import prompt_store
from app.llm.factory import get_gateway
from app.llm.routing import Task
from app.llm.types import AllProvidersFailedError, CallContext
from app.modules.interviews.schemas import InterviewPlan, PlanQuestion

logger = structlog.get_logger(__name__)

BANK_FILE = Path(__file__).with_name("bank.json")
KIND_FOR_TYPE = {"dsa": "coding", "system_design": "design", "behavioral": "behavioral"}
_ORDER = [Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD]
JOB_TEXT_CHARS = 5000


@lru_cache(maxsize=1)
def bank() -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = json.loads(BANK_FILE.read_text(encoding="utf-8"))
    return data


def pick_from_bank(
    type_key: str,
    difficulty: Difficulty,
    count: int,
    *,
    avoid: set[str] = frozenset(),  # type: ignore[assignment]
    rng: random.Random | None = None,
) -> list[dict[str, Any]]:
    """`count` questions, nearest difficulty first, unseen before seen."""
    rng = rng or random.Random()  # noqa: S311 - variety, not security
    pool = bank().get(type_key, [])
    target = _ORDER.index(difficulty)

    def rank(q: dict[str, Any]) -> tuple[int, int, float]:
        distance = abs(_ORDER.index(Difficulty(q["difficulty"])) - target)
        return (q["prompt"] in avoid, distance, rng.random())

    chosen = sorted(pool, key=rank)[:count]
    order = {d: i for i, d in enumerate(_ORDER)}
    chosen.sort(key=lambda q: order[Difficulty(q["difficulty"])])  # warm-up first
    kind = KIND_FOR_TYPE.get(type_key, "technical")
    return [
        PlanQuestion(
            prompt=q["prompt"], focus=q["focus"], kind=kind, expected_points=q["expected_points"]
        ).model_dump()
        for q in chosen
    ]


def fallback_job_plan(job: Job, have: set[str], count: int) -> list[dict[str, Any]]:
    """A sensible job-specific plan without an LLM: experience with the job's main skills,
    one skill the candidate lacks, and one behavioral question."""
    questions: list[PlanQuestion] = [
        PlanQuestion(
            prompt=f"What interests you about the {job.title} role at {job.company_name}, and "
            "which part of your background prepares you best for it?",
            focus="Motivation and fit",
            kind="behavioral",
            expected_points=[
                "Specific link between past work and the role",
                "Knows what the company does",
                "Clear, concise story",
            ],
        )
    ]
    known = [s for s in job.skills if s.lower() in have]
    missing = [s for s in job.skills if s.lower() not in have]
    for skill in known[:2]:
        questions.append(
            PlanQuestion(
                prompt=f"Walk me through a real problem you solved with {skill}. What made it "
                "hard, and what would you do differently today?",
                focus=skill,
                kind="technical",
                expected_points=[
                    "A concrete project and their own role",
                    f"Depth on how {skill} works, not just that it was used",
                    "Trade-offs and lessons learned",
                ],
            )
        )
    for skill in missing[:1]:
        questions.append(
            PlanQuestion(
                prompt=f"This role uses {skill}, which isn't prominent on your resume. How "
                "would you get productive with it in your first month?",
                focus=f"Learning {skill}",
                kind="technical",
                expected_points=[
                    "Honest about the gap",
                    "Concrete learning plan",
                    f"Connects {skill} to something they already know",
                ],
            )
        )
    questions.append(
        PlanQuestion(
            prompt="Tell me about a time you had to deliver under a tight deadline. "
            "How did you decide what to cut?",
            focus="Prioritisation",
            kind="behavioral",
            expected_points=["Situation and stakes", "How they prioritised", "Result"],
        )
    )
    return [q.model_dump() for q in questions[:count]]


async def job_plan(
    job: Job,
    *,
    candidate_text: str,
    have: set[str],
    count: int,
    difficulty: Difficulty,
    ctx: CallContext,
) -> tuple[list[dict[str, Any]], str]:
    """(plan, source) where source is "provider:model" or "fallback"."""
    messages, version = await prompt_store.render(
        "interview_plan",
        count=count,
        difficulty=difficulty.value,
        title=job.title,
        company=job.company_name,
        job_skills=job.skills,
        job_text=job.description_text[:JOB_TEXT_CHARS],
        candidate=candidate_text or "No resume uploaded.",
    )
    ctx.prompt_version = version
    try:
        plan, result = await get_gateway().complete_json(
            Task.INTERVIEW_PLAN, messages, InterviewPlan, ctx=ctx, max_tokens=2000
        )
    except AllProvidersFailedError as exc:
        logger.warning("interview_plan_fallback", job_id=str(job.id), error=str(exc))
        return fallback_job_plan(job, have, count), "fallback"
    questions = [q.model_dump() for q in plan.questions[:count]]
    if len(questions) < count:  # top up rather than run a shorter interview
        extra = fallback_job_plan(job, have, count)
        questions += [q for q in extra if q["prompt"] not in {x["prompt"] for x in questions}]
    return questions[:count], f"{result.provider}:{result.model}"
