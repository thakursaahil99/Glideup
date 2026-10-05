"""Feedback report for a finished interview (background job).

The LLM judges each rubric criterion (1-5) and each answered question (0-10). We then:
- keep only criteria that exist in the interview's rubric, and evidence quotes that really
  appear in the candidate's answers;
- score unanswered questions 0, whatever the model says;
- compute the overall score ourselves: 60% weighted rubric, 40% per-question average. So a
  candidate who answered one question of four can't get a high score from a generous model.
"""

import re
import uuid
from typing import Any

import structlog
from sqlalchemy import select

from app.db.models import Interview, InterviewMessage, InterviewReport, InterviewType, ReportStatus
from app.db.session import session_factory
from app.llm import prompt_store
from app.llm.factory import get_gateway
from app.llm.routing import Task
from app.llm.types import AllProvidersFailedError, CallContext
from app.modules.interviews.schemas import (
    NextPractice,
    ReportDraft,
    ReportResult,
    ScoredCriterion,
    ScoredQuestion,
)

logger = structlog.get_logger(__name__)

RUBRIC_SHARE = 0.6
TRANSCRIPT_CHARS_PER_QUESTION = 6000


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def build_result(
    draft: ReportDraft,
    *,
    rubric: list[dict[str, Any]],
    plan: list[dict[str, Any]],
    answered: set[int],
    candidate_text: str,
    hints_used: int,
    type_keys: set[str],
) -> ReportResult:
    """Ground the model's draft and compute the scores. Pure, so it can be tested."""
    haystack = _normalise(candidate_text)
    by_key = {c.key: c for c in draft.criteria}
    criteria: list[ScoredCriterion] = []
    for item in rubric:
        judged = by_key.get(item["key"])
        evidence = judged.evidence if judged else None
        if evidence and _normalise(evidence) not in haystack:
            evidence = None  # not something the candidate actually said
        criteria.append(
            ScoredCriterion(
                key=item["key"],
                name=item["name"],
                weight=float(item.get("weight", 1)),
                score=judged.score if judged else None,
                evidence=evidence,
                comment=judged.comment if judged else None,
            )
        )
    scored = [c for c in criteria if c.score is not None]
    total_weight = sum(c.weight for c in scored)
    rubric_score = (
        round(100 * sum(c.weight * ((c.score or 1) - 1) / 4 for c in scored) / total_weight)
        if total_weight
        else None
    )

    judged_questions = {q.index: q for q in draft.questions}
    questions: list[ScoredQuestion] = []
    for index, item in enumerate(plan):
        judged_q = judged_questions.get(index)
        is_answered = index in answered
        if not is_answered:
            questions.append(
                ScoredQuestion(index=index, prompt=item["prompt"], focus=item["focus"],
                               answered=False, score=0, feedback="Not answered.")
            )  # fmt: skip
            continue
        fallback_score = round((rubric_score or 50) / 10)
        questions.append(
            ScoredQuestion(
                index=index,
                prompt=item["prompt"],
                focus=item["focus"],
                answered=True,
                score=judged_q.score if judged_q else fallback_score,
                feedback=judged_q.feedback if judged_q else None,
                strengths=judged_q.strengths if judged_q else [],
                improvements=judged_q.improvements if judged_q else [],
            )
        )
    questions_score = (
        round(10 * sum(q.score for q in questions) / len(questions)) if questions else 0
    )
    overall = (
        round(RUBRIC_SHARE * rubric_score + (1 - RUBRIC_SHARE) * questions_score)
        if rubric_score is not None
        else questions_score
    )
    next_practice = draft.next_practice
    if next_practice and next_practice.type not in type_keys:
        next_practice = NextPractice(
            type="behavioral" if "behavioral" in type_keys else sorted(type_keys)[0],
            focus=next_practice.focus,
            reason=next_practice.reason,
        )
    return ReportResult(
        overall_score=overall,
        rubric_score=rubric_score,
        questions_score=questions_score,
        summary=draft.summary,
        criteria=criteria,
        questions=questions,
        strengths=draft.strengths,
        weaknesses=draft.weaknesses,
        tips=draft.tips,
        next_practice=next_practice,
        answered=len(answered),
        total_questions=len(plan),
        hints_used=hints_used,
    )


async def generate_report_job(interview_id: str) -> None:
    async with session_factory()() as session:
        interview = await session.get(Interview, uuid.UUID(interview_id))
        report = await session.get(InterviewReport, uuid.UUID(interview_id))
        if (
            interview is None
            or report is None
            or report.status
            not in (
                ReportStatus.PENDING,
                ReportStatus.GENERATING,
                ReportStatus.FAILED,
            )
        ):
            return
        report.status = ReportStatus.GENERATING
        report.attempts += 1
        report.error = None
        await session.commit()

        messages = list(
            await session.scalars(
                select(InterviewMessage)
                .where(InterviewMessage.interview_id == interview.id)
                .order_by(InterviewMessage.seq)
            )
        )
        types = {t.key: t for t in await session.scalars(select(InterviewType))}
        type_ = types.get(interview.type_key)
        answered: set[int] = set()
        candidate_parts: list[str] = []
        questions: list[dict[str, Any]] = []
        for index, item in enumerate(interview.plan):
            turns = []
            for m in messages:
                if m.question_index != index or m.kind not in (
                    "question",
                    "followup",
                    "answer",
                    "ack",
                ):
                    continue
                content = m.content + (f"\n\n{m.attachment}" if m.attachment else "")
                turns.append({"role": m.role, "content": content})
                if m.role == "candidate" and m.kind == "answer":
                    answered.add(index)
                    candidate_parts.append(content)
            total, kept = 0, []
            for turn in turns:  # keep the prompt bounded on very long answers
                total += len(turn["content"])
                if total > TRANSCRIPT_CHARS_PER_QUESTION:
                    break
                kept.append(turn)
            has_answer = index in answered
            questions.append({**item, "index": index, "turns": kept if has_answer else []})

        prompt_messages, version = await prompt_store.render(
            "interview_report",
            type_name=type_.name if type_ else interview.type_key,
            difficulty=interview.difficulty.value,
            rubric=interview.rubric,
            type_keys=sorted(types),
            hints_used=interview.hints_used,
            questions=questions,
        )
        await session.commit()
        ctx = CallContext(user_id=interview.user_id, prompt_version=version)
        try:
            draft, result = await get_gateway().complete_json(
                Task.INTERVIEW_REPORT, prompt_messages, ReportDraft, ctx=ctx, max_tokens=3000
            )
        except AllProvidersFailedError as exc:
            logger.warning("interview_report_failed", interview_id=interview_id, error=str(exc))
            report.status = ReportStatus.FAILED
            report.error = "Our AI reviewer is unavailable right now. Try again in a few minutes."
            await session.commit()
            return

        scored = build_result(
            draft,
            rubric=interview.rubric,
            plan=interview.plan,
            answered=answered,
            candidate_text="\n".join(candidate_parts),
            hints_used=interview.hints_used,
            type_keys=set(types),
        )
        report.result = scored.model_dump(mode="json")
        report.overall_score = scored.overall_score
        report.prompt_version = version
        report.generated_by = f"{result.provider}:{result.model}"
        report.status = ReportStatus.DONE
        from app.modules.skills.service import award_badges

        await session.flush()
        await award_badges(session, interview.user_id)
        await session.commit()
        logger.info("interview_report_done", interview_id=interview_id, score=scored.overall_score)
