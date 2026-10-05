"""Mock interviews: REST for setup, history and reports; a WebSocket for the live room."""

import asyncio
import uuid
from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.api.v1.interview_schemas import (
    InterviewCreate,
    InterviewDetail,
    InterviewMessageOut,
    InterviewState,
    InterviewSummary,
    InterviewTypeOut,
    ReportOut,
    SocketTicket,
)
from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, ErrorResponse, UnauthorizedError
from app.db.models import (
    Interview,
    InterviewMessage,
    InterviewReport,
    InterviewStatus,
    InterviewType,
    ReportStatus,
)
from app.db.session import session_factory
from app.modules.interviews import engine, service
from app.modules.interviews.report import generate_report_job
from app.modules.interviews.schemas import ReportResult
from app.workers.runtime import dispatch

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/interviews",
    tags=["interviews"],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
ws_router = APIRouter(tags=["interviews"])

TIME_CHECK_S = 5.0


async def _type_names(session: SessionDep) -> dict[str, str]:
    return {t.key: t.name for t in await service.list_types(session, enabled_only=False)}


def _summary(
    interview: Interview, report: InterviewReport | None, names: dict[str, str]
) -> InterviewSummary:
    return InterviewSummary(
        id=interview.id,
        type_key=interview.type_key,
        type_name=names.get(interview.type_key, interview.type_key),
        status=interview.status,
        difficulty=interview.difficulty,
        job_title=interview.job_title,
        company_name=interview.company_name,
        created_at=interview.created_at,
        ended_at=interview.ended_at,
        report_status=report.status if report else None,
        overall_score=report.overall_score if report else None,
    )


async def _detail(session: SessionDep, interview: Interview) -> InterviewDetail:
    messages = await session.scalars(
        select(InterviewMessage)
        .where(InterviewMessage.interview_id == interview.id)
        .order_by(InterviewMessage.seq)
    )
    report = await session.get(InterviewReport, interview.id)
    type_ = await session.get(InterviewType, interview.type_key)
    return InterviewDetail(
        interview=InterviewState.model_validate(engine.interview_state(interview)),
        type_name=type_.name if type_ else interview.type_key,
        messages=[InterviewMessageOut.model_validate(engine.message_out(m)) for m in messages],
        report_status=report.status if report else None,
        overall_score=report.overall_score if report else None,
        error=interview.error,
    )


@router.get("/types", response_model=list[InterviewTypeOut])
async def interview_types(session: SessionDep, _: CurrentUser) -> list[InterviewTypeOut]:
    types = await service.list_types(session)
    await session.commit()
    return [InterviewTypeOut.model_validate(t) for t in types]


@router.post(
    "",
    response_model=InterviewDetail,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
)
async def create_interview(
    body: InterviewCreate, session: SessionDep, user: CurrentUser
) -> InterviewDetail:
    """Set up an interview. Job-specific ones start as `preparing` while the questions are
    written; poll until `ready`, then open the WebSocket and send `start`."""
    interview = await service.create(
        session, user, type_key=body.type_key, difficulty=body.difficulty, job_id=body.job_id
    )
    return await _detail(session, interview)


@router.get("", response_model=list[InterviewSummary])
async def my_interviews(session: SessionDep, user: CurrentUser) -> list[InterviewSummary]:
    names = await _type_names(session)
    return [_summary(i, r, names) for i, r in await service.list_for_user(session, user)]


@router.get("/{interview_id}", response_model=InterviewDetail)
async def get_interview(
    interview_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> InterviewDetail:
    interview = await service.get_owned(session, user, interview_id)
    if engine.time_is_up(interview) and not engine.is_busy(interview.id):

        async def _ignore(_: dict[str, Any]) -> None:
            return None

        async with engine.lock_for(interview.id):
            await engine.finish(session, interview, "time_up", _ignore)
    return await _detail(session, interview)


@router.post(
    "/{interview_id}/ticket",
    response_model=SocketTicket,
    responses={409: {"model": ErrorResponse}},
)
async def socket_ticket(
    interview_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> SocketTicket:
    """A single-use ticket (valid 60 s) for the interview's WebSocket."""
    interview = await service.get_owned(session, user, interview_id)
    if interview.status not in (InterviewStatus.READY, InterviewStatus.IN_PROGRESS):
        raise ConflictError("This interview isn't open.", code="interview_closed")
    ticket = await service.issue_ticket(session, interview)
    base = get_settings().api_public_url.rstrip("/").replace("http", "ws", 1)
    return SocketTicket(
        ticket=ticket,
        url=f"{base}/ws/interviews/{interview.id}",
        expires_in=int(service.TICKET_TTL.total_seconds()),
    )


@router.get("/{interview_id}/report", response_model=ReportOut)
async def get_report(interview_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> ReportOut:
    interview = await service.get_owned(session, user, interview_id)
    report = await session.get(InterviewReport, interview.id)
    if report is None:
        raise ConflictError("The interview hasn't finished yet.", code="not_finished")
    names = await _type_names(session)
    return ReportOut(
        status=report.status,
        overall_score=report.overall_score,
        result=ReportResult.model_validate(report.result) if report.result else None,
        error=report.error,
        generated_by=report.generated_by,
        interview=_summary(interview, report, names),
    )


@router.post(
    "/{interview_id}/report/retry",
    response_model=ReportOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {"model": ErrorResponse}},
)
async def retry_report(
    interview_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> ReportOut:
    interview = await service.get_owned(session, user, interview_id)
    report = await session.get(InterviewReport, interview.id)
    if report is None or report.status != ReportStatus.FAILED:
        raise ConflictError("Only a failed report can be retried.", code="not_failed")
    report.status = ReportStatus.PENDING
    await session.commit()
    from app.modules.interviews import tasks

    dispatch(tasks.generate_report, generate_report_job, str(interview.id))
    return await get_report(interview_id, session, user)


# ------------------------------------------------------------------ WebSocket


class ClientEvent(BaseModel):
    type: Literal["start", "answer", "hint", "skip", "end", "ping"]
    text: str = Field(default="", max_length=engine.MAX_ANSWER_CHARS)
    attachment: str | None = Field(default=None, max_length=engine.MAX_ATTACHMENT_CHARS)
    client_id: str | None = Field(default=None, max_length=64)


@ws_router.websocket("/ws/interviews/{interview_id}")
async def interview_socket(
    websocket: WebSocket,
    interview_id: uuid.UUID,
    ticket: Annotated[str, Query(max_length=2000)] = "",
) -> None:
    """Protocol (JSON both ways).

    Client -> server: {"type": "start" | "answer" | "hint" | "skip" | "end" | "ping",
    "text"?, "attachment"?, "client_id"?}.
    Server -> client: "state" (on connect: interview + transcript), "message",
    "stream_start" / "delta" / "stream_end", "interview" (progress), "ended", "error", "pong".
    """
    settings = get_settings()
    origin = websocket.headers.get("origin")
    if origin and origin.rstrip("/") not in {o.rstrip("/") for o in settings.cors_origins}:
        await websocket.close(code=4403)
        return
    try:
        async with session_factory()() as session:
            user = await service.redeem_ticket(session, ticket, interview_id)
            interview = await session.get(Interview, interview_id)
            if interview is None:  # deleted after the ticket was issued
                raise UnauthorizedError("Interview not found", code="invalid_ticket")
            detail = await _detail(session, interview)
    except UnauthorizedError:
        await websocket.close(code=4401)
        return
    await websocket.accept()

    async def send(event: dict[str, Any]) -> None:
        await websocket.send_json(event)

    await send(
        {"type": "state", **detail.model_dump(mode="json"), "busy": engine.is_busy(interview_id)}
    )
    log = logger.bind(interview_id=str(interview_id), user_id=str(user.id))
    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_json(), timeout=TIME_CHECK_S)
            except TimeoutError:
                await engine.check_time(interview_id, user, send)
                continue
            try:
                event = ClientEvent.model_validate(raw)
            except ValidationError:
                await send(
                    {"type": "error", "code": "bad_event", "message": "Unrecognised message."}
                )
                continue
            try:
                if event.type == "ping":
                    await send({"type": "pong"})
                elif event.type == "start":
                    await engine.start(interview_id, user, send)
                elif event.type == "answer":
                    await engine.answer(
                        interview_id, user, event.text,
                        attachment=event.attachment, client_id=event.client_id, send=send,
                    )  # fmt: skip
                elif event.type == "hint":
                    await engine.hint(interview_id, user, send)
                elif event.type == "skip":
                    await engine.skip(interview_id, user, send)
                elif event.type == "end":
                    await engine.end(interview_id, user, send)
            except AppError as exc:
                await send({"type": "error", "code": exc.code, "message": exc.message})
    except WebSocketDisconnect:
        log.debug("interview_socket_closed")
    except RuntimeError:  # sending on a socket the client already closed
        log.debug("interview_socket_gone")
