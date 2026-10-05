"""The interview conversation, independent of the transport (WebSocket today).

Every action (start, answer, hint, skip, end) runs under a per-interview lock, persists
what happened, and reports progress through `send` as plain dict events. Streaming
replies are saved when they finish, so a dropped connection never loses a turn and a
reconnecting client simply receives the stored transcript.

The interviewer model decides between a follow-up and moving on by ending its reply with
`[[NEXT]]`; the server also moves on when the follow-up budget is spent, so the model can
never trap a candidate on one question. If no model answers at all, the interview still
advances with a neutral acknowledgement instead of getting stuck.
"""

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.models import (
    Interview,
    InterviewMessage,
    InterviewReport,
    InterviewStatus,
    InterviewType,
    ReportStatus,
    User,
)
from app.db.session import session_factory
from app.llm import prompt_store
from app.llm.factory import get_gateway
from app.llm.routing import Task
from app.llm.types import AllProvidersFailedError, CallContext, StreamInterruptedError
from app.modules.interviews import heuristics  # noqa: F401  (registers the mock)
from app.workers.runtime import dispatch

logger = structlog.get_logger(__name__)

Send = Callable[[dict[str, Any]], Awaitable[None]]

MARKER = "[[NEXT]]"
MAX_ANSWER_CHARS = 6000
MAX_ATTACHMENT_CHARS = 20000
REPLY_MAX_TOKENS = 300
HINT_MAX_TOKENS = 150
FALLBACK_ACK = "Thanks, that's helpful. Let's keep going."
MOVE_ON = "Thanks, that covers it. Let's move on."

PERSONAS: dict[str, tuple[str, str]] = {
    "dsa": (
        "senior software engineer",
        "Probe the approach, correctness on edge cases and time/space complexity; once the "
        "approach is clear, ask for code in the code panel.",
    ),
    "system_design": (
        "staff engineer",
        "Probe requirements and scale first, then components, data model, bottlenecks and "
        "trade-offs. Push on the weakest part of the design.",
    ),
    "behavioral": (
        "hiring manager",
        "Probe for any missing STAR part (situation, task, action, result) and for ownership, "
        "growth mindset and collaboration. Ask what THEY did, not the team.",
    ),
    "job_specific": (
        "hiring manager",
        "Probe depth on the role's technologies and ask for concrete examples from their "
        "own experience.",
    ),
}

_locks: dict[uuid.UUID, asyncio.Lock] = {}


class InterviewError(AppError):
    code = "interview_error"


def lock_for(interview_id: uuid.UUID) -> asyncio.Lock:
    return _locks.setdefault(interview_id, asyncio.Lock())


def is_busy(interview_id: uuid.UUID) -> bool:
    lock = _locks.get(interview_id)
    return bool(lock and lock.locked())


def _aware(moment: datetime | None) -> datetime | None:
    return moment.replace(tzinfo=UTC) if moment and moment.tzinfo is None else moment


# ------------------------------------------------------------------ serialisation


def message_out(m: InterviewMessage) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "seq": m.seq,
        "role": m.role,
        "kind": m.kind,
        "question_index": m.question_index,
        "content": m.content,
        "attachment": m.attachment,
        "interrupted": m.interrupted,
        "created_at": (_aware(m.created_at) or datetime.now(UTC)).isoformat(),
    }


def interview_state(i: Interview) -> dict[str, Any]:
    total = len(i.plan or [])
    current = i.plan[i.current_index] if i.plan and i.current_index < total else None
    return {
        "id": str(i.id),
        "status": i.status.value,
        "type_key": i.type_key,
        "difficulty": i.difficulty.value,
        "duration_minutes": i.duration_minutes,
        "current_index": i.current_index,
        "total_questions": total,
        "current_kind": current["kind"] if current else None,
        "followups_used": i.followups_used,
        "max_followups": i.max_followups,
        "hints_used": i.hints_used,
        "started_at": iso(i.started_at),
        "ends_at": iso(i.ends_at),
        "ended_at": iso(i.ended_at),
        "end_reason": i.end_reason,
        "job_title": i.job_title,
        "company_name": i.company_name,
    }


def iso(moment: datetime | None) -> str | None:
    aware = _aware(moment)
    return aware.isoformat() if aware else None


async def _safe(send: Send, event: dict[str, Any]) -> None:
    """The client may be gone; the turn must still complete and be saved."""
    try:
        await send(event)
    except Exception:
        logger.debug("interview_send_dropped", event=event.get("type"))


# ------------------------------------------------------------------ helpers


async def _load(session: AsyncSession, interview_id: uuid.UUID, user_id: uuid.UUID) -> Interview:
    interview = await session.get(Interview, interview_id)
    if interview is None or interview.user_id != user_id:
        raise NotFoundError("Interview not found")
    return interview


async def _add(
    session: AsyncSession,
    interview: Interview,
    role: str,
    kind: str,
    content: str,
    *,
    attachment: str | None = None,
    client_id: str | None = None,
    interrupted: bool = False,
    message_id: uuid.UUID | None = None,
) -> InterviewMessage:
    seq = await session.scalar(
        select(func.coalesce(func.max(InterviewMessage.seq), 0)).where(
            InterviewMessage.interview_id == interview.id
        )
    )
    message = InterviewMessage(
        id=message_id or uuid.uuid4(),
        interview_id=interview.id,
        seq=(seq or 0) + 1,
        role=role,
        kind=kind,
        question_index=interview.current_index if interview.plan else None,
        content=content,
        attachment=attachment,
        client_id=client_id,
        interrupted=interrupted,
        created_at=datetime.now(UTC),
    )
    session.add(message)
    await session.flush()
    return message


async def _turns(session: AsyncSession, interview: Interview) -> list[dict[str, str]]:
    """The current question's exchange, as the prompts expect it."""
    rows = await session.scalars(
        select(InterviewMessage)
        .where(
            InterviewMessage.interview_id == interview.id,
            InterviewMessage.question_index == interview.current_index,
            InterviewMessage.kind.in_(("question", "followup", "answer", "hint")),
        )
        .order_by(InterviewMessage.seq)
    )
    turns = []
    for m in rows:
        content = m.content
        if m.attachment:
            label = "Design notes" if interview_kind(interview) == "design" else "Code"
            content = f"{content}\n\n{label}:\n{m.attachment}".strip()
        turns.append({"role": m.role, "content": content})
    return turns


def interview_kind(interview: Interview) -> str | None:
    if interview.plan and interview.current_index < len(interview.plan):
        kind: str = interview.plan[interview.current_index]["kind"]
        return kind
    return None


def _question_text(interview: Interview) -> str:
    q = interview.plan[interview.current_index]
    total = len(interview.plan)
    prefix = f"Question {interview.current_index + 1} of {total}. " if total > 1 else ""
    tail = " Use the code panel for your code." if q["kind"] == "coding" else ""
    return f"{prefix}{q['prompt']}{tail}"


def _minutes_left(interview: Interview) -> int:
    ends = _aware(interview.ends_at)
    if ends is None:
        return interview.duration_minutes
    return max(0, int((ends - datetime.now(UTC)).total_seconds() // 60))


def time_is_up(interview: Interview) -> bool:
    ends = _aware(interview.ends_at)
    return bool(
        interview.status == InterviewStatus.IN_PROGRESS and ends and datetime.now(UTC) >= ends
    )


# Small models vary the control token ("[NEXT]", "[[ next ]]") and put it anywhere.
_MARKER_RE = re.compile(r"\[\[?\s*NEXT\s*\]\]?", re.IGNORECASE)
_MARKER_FORMS = ("[[NEXT]]", "[NEXT]")
# ...and sometimes start with a transcript-style speaker label.
_LABEL_RE = re.compile(r"^\s*(?:interviewer|assistant)\s*:\s*", re.IGNORECASE)
_LABEL_WAIT = len("interviewer:") + 2


class MarkerFilter:
    """Hide the move-on token (and a leading "Interviewer:" label) from a stream, even
    when they arrive split across chunks."""

    def __init__(self) -> None:
        self.buffer = ""
        self.found = False
        self.started = False  # the leading label has been dealt with
        self.emitted = False  # any visible text sent yet
        self.closing = False  # a marker just ended; drop a straggling "]"

    def _strip_markers(self) -> None:
        if self.closing and self.buffer:
            self.buffer = self.buffer.lstrip("]")
            self.closing = not self.buffer
        matches = list(_MARKER_RE.finditer(self.buffer))
        if matches:
            self.found = True
            # "[[NEXT]" may be followed by its last "]" in the next chunk.
            self.closing = matches[-1].end() == len(self.buffer)
            self.buffer = _MARKER_RE.sub("", self.buffer)

    def feed(self, chunk: str) -> str:
        self.buffer += chunk
        if not self.started:
            if len(self.buffer) < _LABEL_WAIT and "\n" not in self.buffer:
                return ""
            self.buffer = _LABEL_RE.sub("", self.buffer, count=1)
            self.started = True
        self._strip_markers()
        hold = 0
        upper = self.buffer.upper()
        for size in range(min(len(_MARKER_FORMS[0]) - 1, len(upper)), 0, -1):
            tail = upper[-size:]
            if any(form.startswith(tail) for form in _MARKER_FORMS):
                hold = size
                break
        out = self.buffer[: len(self.buffer) - hold]
        self.buffer = self.buffer[len(self.buffer) - hold :]
        if not self.emitted:
            out = out.lstrip()
        self.emitted = self.emitted or bool(out)
        return out

    def finish(self) -> str:
        if not self.started:
            self.buffer = _LABEL_RE.sub("", self.buffer, count=1)
        self._strip_markers()
        rest, self.buffer = self.buffer, ""
        if rest.startswith("["):
            return ""
        return rest if self.emitted else rest.lstrip()


def decide_move_on(said_next: bool, text: str, followups_left: int) -> bool:
    """Whether the interviewer's reply closes the current question.

    A reply that ends with a question is a follow-up, even if the model also emitted the
    move-on token (small models do both): moving on would leave its question unanswered.
    """
    if followups_left <= 0:
        return True
    asks = text.rstrip().endswith("?")
    return said_next and not asks


# ------------------------------------------------------------------ actions


async def start(interview_id: uuid.UUID, user: User, send: Send) -> None:
    """Begin the clock and ask the first question. Idempotent."""
    async with lock_for(interview_id), session_factory()() as session:
        interview = await _load(session, interview_id, user.id)
        if interview.status != InterviewStatus.READY:
            return
        type_ = await session.get(InterviewType, interview.type_key)
        now = datetime.now(UTC)
        interview.status = InterviewStatus.IN_PROGRESS
        interview.started_at = now
        interview.ends_at = now + timedelta(minutes=interview.duration_minutes)
        name = (user.name or "").split(" ")[0]
        total = len(interview.plan)
        role = (
            f" for the {interview.job_title} role at {interview.company_name}"
            if interview.job_title
            else ""
        )
        intro = (
            f"Hi{' ' + name if name else ''}! I'll be your interviewer for this "
            f"{type_.name if type_ else 'mock'} interview{role}. We have {total} "
            f"question{'s' if total != 1 else ''} and {interview.duration_minutes} minutes. "
            "Think out loud, ask clarifying questions, and ask for a hint if you get stuck."
        )
        first = await _add(session, interview, "interviewer", "intro", intro)
        question = await _add(
            session, interview, "interviewer", "question", _question_text(interview)
        )
        await session.commit()
        for message in (first, question):
            await _safe(send, {"type": "message", "message": message_out(message)})
        await _safe(send, {"type": "interview", "interview": interview_state(interview)})


async def answer(
    interview_id: uuid.UUID,
    user: User,
    text: str,
    *,
    attachment: str | None,
    client_id: str | None,
    send: Send,
) -> None:
    text = text.strip()[:MAX_ANSWER_CHARS]
    attachment = (attachment or "").strip()[:MAX_ATTACHMENT_CHARS] or None
    if not text and not attachment:
        raise InterviewError("Write an answer first.", code="empty_answer")
    async with lock_for(interview_id), session_factory()() as session:
        interview = await _require_running(session, interview_id, user, send)
        if interview is None:
            return
        if client_id and await session.scalar(
            select(InterviewMessage.id).where(
                InterviewMessage.interview_id == interview.id,
                InterviewMessage.client_id == client_id,
            )
        ):
            return  # a resend of an answer we already have
        message = await _add(
            session,
            interview,
            "candidate",
            "answer",
            text,
            attachment=attachment,
            client_id=client_id,
        )
        await session.commit()
        await _safe(send, {"type": "message", "message": message_out(message)})
        await _reply(session, interview, user, send)


async def hint(interview_id: uuid.UUID, user: User, send: Send) -> None:
    async with lock_for(interview_id), session_factory()() as session:
        interview = await _require_running(session, interview_id, user, send)
        if interview is None:
            return
        type_ = await session.get(InterviewType, interview.type_key)
        question = interview.plan[interview.current_index]
        hints_on_question = await session.scalar(
            select(func.count()).where(
                InterviewMessage.interview_id == interview.id,
                InterviewMessage.question_index == interview.current_index,
                InterviewMessage.kind == "hint",
            )
        )
        messages, version = await prompt_store.render(
            "interview_hint",
            type_name=type_.name if type_ else interview.type_key,
            question=question["prompt"],
            expected_points=question["expected_points"],
            hint_number=(hints_on_question or 0) + 1,
            turns=await _turns(session, interview),
        )
        await session.commit()  # no transaction open while the model streams
        points = question["expected_points"] or ["Break the problem into smaller steps."]
        fallback = f"Think about this: {points[min(hints_on_question or 0, len(points) - 1)]}"
        content, interrupted, _ = await _stream(
            Task.INTERVIEW_HINT, messages, version, user, send, "hint", interview, fallback,
            max_tokens=HINT_MAX_TOKENS,
        )  # fmt: skip
        interview.hints_used += 1
        await _store_streamed(session, interview, "hint", content, interrupted, send)
        await session.commit()
        await _safe(send, {"type": "interview", "interview": interview_state(interview)})


async def skip(interview_id: uuid.UUID, user: User, send: Send) -> None:
    async with lock_for(interview_id), session_factory()() as session:
        interview = await _require_running(session, interview_id, user, send)
        if interview is None:
            return
        message = await _add(
            session, interview, "candidate", "skip", "I'd like to skip this question."
        )
        await session.commit()
        await _safe(send, {"type": "message", "message": message_out(message)})
        await _advance(session, interview, send)
        await session.commit()


async def end(interview_id: uuid.UUID, user: User, send: Send, reason: str = "ended_early") -> None:
    async with lock_for(interview_id), session_factory()() as session:
        interview = await _load(session, interview_id, user.id)
        if interview.status != InterviewStatus.IN_PROGRESS:
            return
        await finish(session, interview, reason, send)


async def check_time(interview_id: uuid.UUID, user: User, send: Send) -> None:
    """Called periodically by the transport: end the interview when time runs out."""
    lock = lock_for(interview_id)
    if lock.locked():
        return  # a turn is in progress; it checks the time itself
    async with lock, session_factory()() as session:
        interview = await _load(session, interview_id, user.id)
        if time_is_up(interview):
            await finish(session, interview, "time_up", send)


# ------------------------------------------------------------------ internals


async def _require_running(
    session: AsyncSession, interview_id: uuid.UUID, user: User, send: Send
) -> Interview | None:
    interview = await _load(session, interview_id, user.id)
    if interview.status == InterviewStatus.READY:
        raise ConflictError("Start the interview first.", code="not_started")
    if interview.status != InterviewStatus.IN_PROGRESS:
        raise ConflictError("This interview has ended.", code="interview_ended")
    if time_is_up(interview):
        await finish(session, interview, "time_up", send)
        return None
    return interview


async def _stream(
    task: str,
    messages: list[Any],
    version: str,
    user: User,
    send: Send,
    kind: str,
    interview: Interview,
    fallback: str,
    *,
    max_tokens: int,
) -> tuple[str, bool, bool]:
    """Stream a reply to the client. Returns (text, interrupted, moved_on_marker)."""
    stream_id = str(uuid.uuid4())
    await _safe(
        send,
        {
            "type": "stream_start",
            "id": stream_id,
            "kind": kind,
            "question_index": interview.current_index,
        },
    )
    marker = MarkerFilter()
    parts: list[str] = []
    interrupted = False
    ctx = CallContext(user_id=user.id, prompt_version=version)
    try:
        async for delta in get_gateway().stream(task, messages, ctx=ctx, max_tokens=max_tokens):
            visible = marker.feed(delta)
            if visible:
                parts.append(visible)
                await _safe(send, {"type": "delta", "id": stream_id, "text": visible})
    except StreamInterruptedError:
        interrupted = True
    except AllProvidersFailedError as exc:
        logger.warning("interviewer_unavailable", task=task, error=str(exc))
        parts = [fallback]
        await _safe(send, {"type": "delta", "id": stream_id, "text": fallback})
        interrupted = True
    tail = marker.finish()
    if tail:
        parts.append(tail)
        await _safe(send, {"type": "delta", "id": stream_id, "text": tail})
    text = "".join(parts).strip()
    return text or fallback, interrupted, marker.found


async def _store_streamed(
    session: AsyncSession,
    interview: Interview,
    kind: str,
    content: str,
    interrupted: bool,
    send: Send,
) -> InterviewMessage:
    message = await _add(session, interview, "interviewer", kind, content, interrupted=interrupted)
    await session.flush()
    await _safe(send, {"type": "stream_end", "message": message_out(message)})
    return message


async def _reply(session: AsyncSession, interview: Interview, user: User, send: Send) -> None:
    type_ = await session.get(InterviewType, interview.type_key)
    question = interview.plan[interview.current_index]
    persona, guidance = PERSONAS.get(interview.type_key, PERSONAS["job_specific"])
    if interview.job_title and interview.type_key == "job_specific":
        persona = f"hiring manager for the {interview.job_title} role at {interview.company_name}"
    followups_left = max(0, interview.max_followups - interview.followups_used)
    if followups_left == 0:
        # Follow-up budget spent: move on without a model call (faster, and the model can't
        # ask one more question that would go unanswered).
        message = await _add(session, interview, "interviewer", "ack", MOVE_ON)
        await session.flush()
        await _safe(send, {"type": "message", "message": message_out(message)})
        await _advance(session, interview, send)
        await session.commit()
        return
    messages, version = await prompt_store.render(
        "interviewer",
        persona=persona,
        type_name=type_.name if type_ else interview.type_key,
        difficulty=interview.difficulty.value,
        number=interview.current_index + 1,
        total=len(interview.plan),
        question=question["prompt"],
        expected_points=question["expected_points"],
        followups_left=followups_left,
        minutes_left=_minutes_left(interview),
        focus_guidance=guidance,
        turns=await _turns(session, interview),
    )
    await session.commit()  # no transaction open while the model streams
    content, interrupted, said_next = await _stream(
        Task.INTERVIEWER, messages, version, user, send, "followup", interview, FALLBACK_ACK,
        max_tokens=REPLY_MAX_TOKENS,
    )  # fmt: skip
    move_on = interrupted or decide_move_on(said_next, content, followups_left)
    await _store_streamed(
        session, interview, "ack" if move_on else "followup", content, interrupted, send
    )
    if move_on:
        await _advance(session, interview, send)
    else:
        interview.followups_used += 1
        await _safe(send, {"type": "interview", "interview": interview_state(interview)})
    await session.commit()


async def _advance(session: AsyncSession, interview: Interview, send: Send) -> None:
    interview.current_index += 1
    interview.followups_used = 0
    if interview.current_index >= len(interview.plan) or time_is_up(interview):
        await finish(
            session, interview, "finished" if not time_is_up(interview) else "time_up", send
        )
        return
    question = await _add(session, interview, "interviewer", "question", _question_text(interview))
    await session.flush()
    await _safe(send, {"type": "message", "message": message_out(question)})
    await _safe(send, {"type": "interview", "interview": interview_state(interview)})


CLOSING = {
    "finished": "That's all my questions. Thank you, that was a good conversation!",
    "time_up": "We're out of time, so let's stop here. Thank you!",
    "ended_early": "No problem, we'll end here. Thank you!",
}


async def finish(session: AsyncSession, interview: Interview, reason: str, send: Send) -> None:
    """Close the interview and queue its report. Callers hold the interview lock (or run
    where no client is connected, e.g. the expiry job)."""
    interview.current_index = min(interview.current_index, max(0, len(interview.plan) - 1))
    answered = await session.scalar(
        select(func.count()).where(
            InterviewMessage.interview_id == interview.id,
            InterviewMessage.role == "candidate",
            InterviewMessage.kind == "answer",
        )
    )
    closing = CLOSING.get(reason, CLOSING["finished"]) + (
        " I'm writing your feedback report now; it'll be ready in a minute or two."
        if answered
        else " There were no answers to give feedback on this time."
    )
    message = await _add(session, interview, "interviewer", "closing", closing)
    interview.status = InterviewStatus.COMPLETED
    interview.ended_at = datetime.now(UTC)
    interview.end_reason = reason
    report = await session.get(InterviewReport, interview.id)
    if report is None:
        report = InterviewReport(interview_id=interview.id, status=ReportStatus.PENDING)
        session.add(report)
    report.status = ReportStatus.PENDING if answered else ReportStatus.SKIPPED
    await session.commit()
    await _safe(send, {"type": "message", "message": message_out(message)})
    await _safe(send, {"type": "ended", "interview": interview_state(interview)})
    if answered:
        from app.modules.interviews import report as report_module
        from app.modules.interviews import tasks

        dispatch(tasks.generate_report, report_module.generate_report_job, str(interview.id))
    logger.info("interview_finished", interview_id=str(interview.id), reason=reason)
