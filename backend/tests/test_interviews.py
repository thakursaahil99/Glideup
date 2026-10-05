"""Mock interviews: streaming gateway, the WebSocket room, reports, housekeeping, and
the interview / prompt admin screens."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from httpx_ws import AsyncWebSocketSession, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models import (
    AuditLog,
    Interview,
    InterviewMessage,
    InterviewReport,
    Job,
    JobSource,
    ReportStatus,
)
from app.llm import prompt_store
from app.llm.circuit import CircuitRegistry
from app.llm.gateway import LLMGateway
from app.llm.types import (
    AllProvidersFailedError,
    CompletionRequest,
    CompletionResult,
    LLMError,
    Message,
    StreamInterruptedError,
)
from app.main import create_app
from app.modules.interviews.engine import MOVE_ON, MarkerFilter, decide_move_on
from app.modules.interviews.report import build_result
from app.modules.interviews.schemas import CriterionScore, NextPractice, QuestionScore, ReportDraft
from app.modules.interviews.service import expire_due_job
from app.workers.runtime import drain_inline_jobs
from tests.conftest import ROOT_ADMIN_EMAIL, LoginFn, UseSettings
from tests.test_jobs import FakePlugin, fake, fake_source, jobs_by_ext, posting  # noqa: F401

LONG = (
    "I led the migration of our billing service to Postgres. I benchmarked three options, "
    "wrote the plan, ran it behind a feature flag and cut costs by 30 percent."
)

# --- unit: stream marker, scoring ---


@pytest.mark.parametrize(
    ("chunks", "visible", "found"),
    [
        (["Interviewer: Can", " you elaborate?"], "Can you elaborate?", False),  # label dropped
        (["[NEXT] What specific", " changes?"], "What specific changes?", True),  # variant
        (["Thanks, good.\n[[NEXT]", "]"], "Thanks, good.\n", True),  # last "]" comes late
        (["Done. [[next]]"], "Done. ", True),
    ],
)
def test_marker_variants_from_small_models(chunks: list[str], visible: str, found: bool) -> None:
    marker = MarkerFilter()
    assert "".join(marker.feed(c) for c in chunks) + marker.finish() == visible
    assert marker.found is found


def test_a_reply_that_asks_something_is_a_follow_up() -> None:
    asks = "Thanks. What changed after?"
    assert decide_move_on(said_next=True, text=asks, followups_left=2) is False
    assert decide_move_on(said_next=True, text="Thanks, that is clear.", followups_left=2) is True
    assert decide_move_on(said_next=False, text="Why?", followups_left=0) is True


def test_marker_is_hidden_even_when_split_across_chunks() -> None:
    marker = MarkerFilter()
    out = "".join(marker.feed(c) for c in ["Thanks, good.", "\n[", "[NE", "XT]", "]"])
    out += marker.finish()
    assert out == "Thanks, good.\n"
    assert marker.found
    plain = MarkerFilter()
    text = "".join(plain.feed(c) for c in ["Arrays [1, 2]", " work"]) + plain.finish()
    assert text == "Arrays [1, 2] work"
    assert not plain.found


RUBRIC = [
    {"key": "action", "name": "Action", "description": "", "weight": 2},
    {"key": "result", "name": "Result", "description": "", "weight": 1},
]
PLAN = [
    {"prompt": "Q1", "focus": "A", "kind": "behavioral", "expected_points": []},
    {"prompt": "Q2", "focus": "B", "kind": "behavioral", "expected_points": []},
]


def test_report_scores_are_computed_and_grounded() -> None:
    draft = ReportDraft(
        summary="Good.",
        criteria=[
            CriterionScore(key="action", score=5, evidence="I ran a benchmark"),
            CriterionScore(key="result", score=3, evidence="we tripled revenue"),  # not said
            CriterionScore(key="invented", score=5),
        ],
        questions=[QuestionScore(index=0, score=8), QuestionScore(index=1, score=9)],
        next_practice=NextPractice(type="nonsense", focus="STAR"),
    )
    result = build_result(
        draft,
        rubric=RUBRIC,
        plan=PLAN,
        answered={0},  # question 1 was never answered...
        candidate_text="Well, I ran a benchmark first.",
        hints_used=1,
        type_keys={"behavioral", "dsa"},
    )
    assert [c.key for c in result.criteria] == ["action", "result"]  # invented one dropped
    assert result.criteria[0].evidence == "I ran a benchmark"
    assert result.criteria[1].evidence is None  # not something they said
    assert result.rubric_score == round(100 * (2 * 1 + 1 * 0.5) / 3)  # 83
    assert [q.score for q in result.questions] == [
        8,
        0,
    ]  # ...so it scores 0 whatever the model said
    assert result.questions_score == 40
    assert result.overall_score == round(0.6 * 83 + 0.4 * 40)
    assert result.next_practice is not None
    assert result.next_practice.type == "behavioral"
    assert (result.answered, result.total_questions, result.hints_used) == (1, 2, 1)


# --- unit: streaming gateway ---


class _Flaky:
    def __init__(self, name: str, fail_after: int | None, chunks: list[str]) -> None:
        self.name, self.fail_after, self.chunks = name, fail_after, chunks

    async def complete(self, request: CompletionRequest, model: str) -> CompletionResult:
        raise NotImplementedError

    async def embed(self, texts: list[str], model: str) -> Any:
        raise NotImplementedError

    async def stream(
        self, request: CompletionRequest, model: str
    ) -> AsyncIterator[str | CompletionResult]:
        for n, chunk in enumerate(self.chunks):
            if self.fail_after is not None and n >= self.fail_after:
                raise LLMError("boom")
            yield chunk
        yield CompletionResult("".join(self.chunks), self.name, model, 1, 1)


class _NoRecord:
    async def record(self, usage: object) -> None:
        return None


def _gateway(settings: Settings, **providers: _Flaky) -> LLMGateway:
    routes = {"interviewer": [f"{name}:m" for name in providers]}
    custom = settings.model_copy(update={"llm_routes": routes, "llm_allow_mock_fallback": False})
    return LLMGateway(custom, dict(providers), _NoRecord(), CircuitRegistry(5, 30))


async def test_stream_falls_back_only_before_the_first_token(settings: Settings) -> None:
    messages = [Message("user", "hi")]
    gateway = _gateway(settings, a=_Flaky("a", 0, ["x"]), b=_Flaky("b", None, ["Hel", "lo"]))
    assert [d async for d in gateway.stream("interviewer", messages)] == ["Hel", "lo"]

    broken = _gateway(settings, a=_Flaky("a", 1, ["Hel", "lo"]), b=_Flaky("b", None, ["no"]))
    received: list[str] = []

    async def consume() -> None:
        async for delta in broken.stream("interviewer", messages):
            received.append(delta)

    with pytest.raises(StreamInterruptedError) as interrupted:
        await consume()
    assert received == ["Hel"]
    assert interrupted.value.partial == "Hel"

    dead = _gateway(settings, a=_Flaky("a", 0, ["x"]))
    with pytest.raises(AllProvidersFailedError):
        async for _ in dead.stream("interviewer", messages):
            pass


# --- the live room ---


@asynccontextmanager
async def ws_app(settings: Settings) -> AsyncIterator[AsyncClient]:
    """A client that speaks WebSocket to the app in-process. Opened inside each test: the
    transport must be closed by the task that opened it, which fixtures don't guarantee."""
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    async with AsyncClient(transport=ASGIWebSocketTransport(app), base_url="http://test") as c:
        yield c


async def until(ws: AsyncWebSocketSession, *types: str) -> list[dict[str, Any]]:
    """Read events until one of `types` arrives; return everything read."""
    seen: list[dict[str, Any]] = []
    while True:
        event: dict[str, Any] = await asyncio.wait_for(ws.receive_json(), timeout=10)
        seen.append(event)
        if event["type"] in types:
            return seen


async def new_interview(
    client: AsyncClient, headers: dict[str, str], **body: Any
) -> dict[str, Any]:
    response = await client.post("/api/v1/interviews", json=body, headers=headers)
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


async def ticket_path(client: AsyncClient, headers: dict[str, str], interview_id: str) -> str:
    response = await client.post(f"/api/v1/interviews/{interview_id}/ticket", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["url"] == f"ws://localhost:8000/ws/interviews/{interview_id}"
    return f"/ws/interviews/{interview_id}?ticket={body['ticket']}"


async def test_types_and_creation(client: AsyncClient, login: LoginFn) -> None:
    headers = await login("candidate@example.com")
    types = (await client.get("/api/v1/interviews/types", headers=headers)).json()
    assert [t["key"] for t in types] == ["dsa", "system_design", "behavioral", "job_specific"]

    created = await new_interview(client, headers, type_key="behavioral", difficulty="easy")
    state = created["interview"]
    assert state["status"] == "ready"
    assert state["total_questions"] == 4
    assert created["messages"] == []
    assert created["type_name"] == "Behavioral"

    # The next behavioral interview avoids the questions just asked where it can.
    async with AsyncSession_() as session:
        first = await session.get(Interview, uuid.UUID(state["id"]))
        assert first is not None
        asked = {q["prompt"] for q in first.plan}
    again = await new_interview(client, headers, type_key="behavioral", difficulty="easy")
    async with AsyncSession_() as session:
        second = await session.get(Interview, uuid.UUID(again["interview"]["id"]))
        assert second is not None
        assert len(asked & {q["prompt"] for q in second.plan}) <= 1  # bank has 8 behavioral

    bad = await client.post(
        "/api/v1/interviews", json={"type_key": "job_specific"}, headers=headers
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "job_required"
    assert (
        await client.post("/api/v1/interviews", json={"type_key": "nope"}, headers=headers)
    ).status_code == 404


def AsyncSession_() -> AsyncSession:  # noqa: N802 - reads like a class at call sites
    from app.db.session import session_factory

    return session_factory()()


async def test_full_interview_over_the_websocket(
    client: AsyncClient, settings: Settings, login: LoginFn
) -> None:
    ws: AsyncWebSocketSession
    async with ws_app(settings) as room:
        headers = await login("candidate@example.com")
        created = await new_interview(client, headers, type_key="behavioral")
        interview_id = created["interview"]["id"]
        path = await ticket_path(client, headers, interview_id)

        async with aconnect_ws(path, room) as ws:
            state = await ws.receive_json()
            assert state["type"] == "state"
            assert state["interview"]["status"] == "ready"

            await ws.send_json({"type": "answer", "text": "too early"})
            error = (await until(ws, "error"))[-1]
            assert error["code"] == "not_started"

            await ws.send_json({"type": "start"})
            events = await until(ws, "interview")
            kinds = [e["message"]["kind"] for e in events if e["type"] == "message"]
            assert kinds == ["intro", "question"]
            assert events[-1]["interview"]["status"] == "in_progress"

            # A short answer gets a streamed follow-up on the same question.
            await ws.send_json({"type": "answer", "text": "We used Redis.", "client_id": "a1"})
            events = await until(ws, "interview")
            types = [e["type"] for e in events]
            assert types[:2] == ["message", "stream_start"]
            assert "delta" in types
            end = next(e for e in events if e["type"] == "stream_end")
            streamed = "".join(e["text"] for e in events if e["type"] == "delta")
            assert end["message"]["kind"] == "followup"
            assert end["message"]["content"] == streamed.strip()
            assert events[-1]["interview"]["followups_used"] == 1

            # Resending the same answer (e.g. after a reconnect) is ignored.
            await ws.send_json({"type": "answer", "text": "We used Redis.", "client_id": "a1"})
            await ws.send_json({"type": "ping"})
            assert (await until(ws, "pong"))[-1]["type"] == "pong"

            # A detailed answer moves on; the [[NEXT]] token never reaches the client.
            await ws.send_json({"type": "answer", "text": LONG, "client_id": "a2"})
            events = await until(ws, "interview")
            assert all("[[" not in e.get("text", "") for e in events)
            ack = next(e for e in events if e["type"] == "stream_end")
            assert ack["message"]["kind"] == "ack"
            question = [e for e in events if e["type"] == "message"][-1]["message"]
            assert question["kind"] == "question"
            assert question["content"].startswith("Question 2 of 4.")

            await ws.send_json({"type": "hint"})
            events = await until(ws, "interview")
            assert next(e for e in events if e["type"] == "stream_end")["message"]["kind"] == "hint"
            assert events[-1]["interview"]["hints_used"] == 1

            await ws.send_json({"type": "skip"})
            events = await until(ws, "interview")
            assert events[-1]["interview"]["current_index"] == 2

            await ws.send_json({"type": "end"})
            events = await until(ws, "ended")
            assert events[-1]["interview"]["end_reason"] == "ended_early"

        await drain_inline_jobs()
        detail = (await client.get(f"/api/v1/interviews/{interview_id}", headers=headers)).json()
        assert detail["interview"]["status"] == "completed"
        assert [m["kind"] for m in detail["messages"]].count("answer") == 2

        report = (
            await client.get(f"/api/v1/interviews/{interview_id}/report", headers=headers)
        ).json()
        assert report["status"] == "done"
        result = report["result"]
        assert result["answered"] == 1  # only question 1 got answers; 2 was skipped
        assert [q["answered"] for q in result["questions"]] == [True, False, False, False]
        assert result["questions"][1]["score"] == 0
        assert result["hints_used"] == 1
        assert {c["key"] for c in result["criteria"]} >= {"action", "result", "ownership"}
        assert report["overall_score"] == result["overall_score"]

        history = (await client.get("/api/v1/interviews", headers=headers)).json()
        assert history[0]["report_status"] == "done"
        assert history[0]["overall_score"] == result["overall_score"]


async def test_spent_follow_up_budget_moves_on_without_a_model_call(
    client: AsyncClient, settings: Settings, login: LoginFn, session: AsyncSession
) -> None:
    headers = await login("candidate@example.com")
    interview_id = (await new_interview(client, headers, type_key="behavioral"))["interview"]["id"]
    interview = await session.get(Interview, uuid.UUID(interview_id))
    assert interview is not None
    interview.max_followups = 0
    await session.commit()
    ws: AsyncWebSocketSession
    async with ws_app(settings) as room:
        path = await ticket_path(client, headers, interview_id)
        async with aconnect_ws(path, room) as ws:
            await ws.receive_json()
            await ws.send_json({"type": "start"})
            await until(ws, "interview")
            await ws.send_json({"type": "answer", "text": "Short."})
            events = await until(ws, "interview")
    assert "stream_start" not in [e["type"] for e in events]
    candidate, ack, question = (e["message"] for e in events if e["type"] == "message")
    assert candidate["role"] == "candidate"
    assert (ack["kind"], ack["content"]) == ("ack", MOVE_ON)
    assert question["kind"] == "question"


async def test_socket_tickets_are_single_use_and_origin_checked(
    client: AsyncClient, settings: Settings, login: LoginFn
) -> None:
    ws: AsyncWebSocketSession
    async with ws_app(settings) as room:
        headers = await login("candidate@example.com")
        interview_id = (await new_interview(client, headers, type_key="dsa"))["interview"]["id"]
        path = await ticket_path(client, headers, interview_id)
        async with aconnect_ws(path, room) as ws:
            assert (await ws.receive_json())["type"] == "state"
        with pytest.raises(Exception):  # noqa: B017,PT011 - rejected before accept
            async with aconnect_ws(path, room):
                pass
        other = await ticket_path(client, headers, interview_id)
        with pytest.raises(Exception):  # noqa: B017,PT011
            async with aconnect_ws(other, room, headers={"Origin": "https://evil.example"}):
                pass
        with pytest.raises(Exception):  # noqa: B017,PT011
            async with aconnect_ws(f"/ws/interviews/{interview_id}?ticket=forged", room):
                pass

        stranger = await login("stranger@example.com")
        stolen = await client.post(f"/api/v1/interviews/{interview_id}/ticket", headers=stranger)
        assert stolen.status_code == 404


@pytest.fixture
async def a_job(session: AsyncSession, fake: FakePlugin, fake_source: JobSource) -> Job:  # noqa: F811
    from app.modules.jobs.ingestion import ingest_source

    body = "<p>Python, Kafka and PostgreSQL at scale.</p>"
    fake.scopes = {"fake:a": [posting("py", title="Senior Python Engineer", body=body)]}
    await ingest_source("fake")
    await drain_inline_jobs()
    return (await jobs_by_ext(session))["py"]


async def test_job_specific_interviews_are_prepared_in_the_background(
    client: AsyncClient, login: LoginFn, a_job: Job
) -> None:
    headers = await login("candidate@example.com")
    created = await new_interview(client, headers, type_key="job_specific", job_id=str(a_job.id))
    assert created["interview"]["status"] in ("preparing", "ready")
    assert created["interview"]["job_title"] == "Senior Python Engineer"
    await drain_inline_jobs()
    detail = (
        await client.get(f"/api/v1/interviews/{created['interview']['id']}", headers=headers)
    ).json()
    assert detail["interview"]["status"] == "ready"
    assert detail["interview"]["total_questions"] == 4


async def test_daily_limit(client: AsyncClient, login: LoginFn, use_settings: UseSettings) -> None:
    headers = await login("candidate@example.com")
    use_settings(interviews_daily_limit=1)
    await new_interview(client, headers, type_key="dsa")
    again = await client.post("/api/v1/interviews", json={"type_key": "dsa"}, headers=headers)
    assert again.status_code == 429
    assert again.json()["error"]["code"] == "quota_exceeded"


async def test_time_limit_ends_the_interview(
    client: AsyncClient, settings: Settings, login: LoginFn, session: AsyncSession
) -> None:
    ws: AsyncWebSocketSession
    async with ws_app(settings) as room:
        headers = await login("candidate@example.com")
        interview_id = (await new_interview(client, headers, type_key="dsa"))["interview"]["id"]
        async with aconnect_ws(await ticket_path(client, headers, interview_id), room) as ws:
            await ws.receive_json()
            await ws.send_json({"type": "start"})
            await until(ws, "interview")
            await ws.send_json({"type": "answer", "text": LONG})
            await until(ws, "interview")

        interview = await session.get(Interview, uuid.UUID(interview_id))
        assert interview is not None
        interview.ends_at = datetime.now(UTC) - timedelta(minutes=1)
        await session.commit()

        detail = (await client.get(f"/api/v1/interviews/{interview_id}", headers=headers)).json()
        assert detail["interview"]["status"] == "completed"
        assert detail["interview"]["end_reason"] == "time_up"
        assert detail["messages"][-1]["kind"] == "closing"
        await drain_inline_jobs()
        report = await session.get(InterviewReport, uuid.UUID(interview_id))
        await session.refresh(report)
        assert report is not None
        assert report.status == ReportStatus.DONE


async def test_expiry_job_and_unanswered_interviews(
    client: AsyncClient, settings: Settings, login: LoginFn, session: AsyncSession
) -> None:
    ws: AsyncWebSocketSession
    async with ws_app(settings) as room:
        headers = await login("candidate@example.com")
        interview_id = (await new_interview(client, headers, type_key="behavioral"))["interview"][
            "id"
        ]
        async with aconnect_ws(await ticket_path(client, headers, interview_id), room) as ws:
            await ws.receive_json()
            await ws.send_json({"type": "start"})
            await until(ws, "interview")
        interview = await session.get(Interview, uuid.UUID(interview_id))
        assert interview is not None
        interview.ends_at = datetime.now(UTC) - timedelta(minutes=10)
        await session.commit()

        assert await expire_due_job() == 1
        report = await session.get(InterviewReport, uuid.UUID(interview_id))
        assert report is not None
        assert report.status == ReportStatus.SKIPPED  # nothing was answered: no LLM call, no score
        closing = await session.scalar(
            select(InterviewMessage.content)
            .where(InterviewMessage.interview_id == interview.id)
            .order_by(InterviewMessage.seq.desc())
        )
        assert closing is not None
        assert "no answers" in closing
        assert await expire_due_job() == 0


async def test_failed_report_can_be_retried(
    client: AsyncClient, login: LoginFn, session: AsyncSession, use_settings: UseSettings
) -> None:
    headers = await login("candidate@example.com")
    interview_id = (await new_interview(client, headers, type_key="dsa"))["interview"]["id"]
    assert (
        await client.get(f"/api/v1/interviews/{interview_id}/report", headers=headers)
    ).status_code == 409
    session.add(InterviewReport(interview_id=uuid.UUID(interview_id), status=ReportStatus.FAILED))
    await session.commit()
    retried = await client.post(f"/api/v1/interviews/{interview_id}/report/retry", headers=headers)
    assert retried.status_code == 202
    assert retried.json()["status"] in ("pending", "generating", "done")


# --- admin ---


async def test_admin_configures_interview_types(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    from app.core.rbac import Role

    support = await login("helper@example.com", Role.SUPPORT)
    assert (await client.get("/api/v1/admin/interview-types", headers=support)).status_code == 403
    editor = await login("editor@example.com", Role.CONTENT_EDITOR)
    types = (await client.get("/api/v1/admin/interview-types", headers=editor)).json()
    behavioral = next(t for t in types if t["key"] == "behavioral")
    assert {c["key"] for c in behavioral["rubric"]} >= {"situation", "action", "result"}

    rubric = [{"key": "star", "name": "STAR", "description": "Uses STAR", "weight": 2}]
    updated = await client.patch(
        "/api/v1/admin/interview-types/behavioral",
        json={"duration_minutes": 20, "question_count": 3, "rubric": rubric},
        headers=editor,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["rubric"] == [{**rubric[0]}]
    entry = await session.scalar(
        select(AuditLog).where(AuditLog.action == "interview_type.updated")
    )
    assert entry is not None
    assert entry.before is not None
    assert entry.after is not None
    assert entry.before["duration_minutes"] == 30
    assert entry.after["duration_minutes"] == 20

    too_many = await client.patch(
        "/api/v1/admin/interview-types/system_design", json={"question_count": 9}, headers=editor
    )
    assert too_many.json()["error"]["code"] == "not_enough_questions"
    duplicate = await client.patch(
        "/api/v1/admin/interview-types/dsa", json={"rubric": rubric + rubric}, headers=editor
    )
    assert duplicate.status_code == 422
    bad_key = [{"key": "Bad Key", "name": "x", "weight": 1}]
    assert (
        await client.patch(
            "/api/v1/admin/interview-types/dsa", json={"rubric": bad_key}, headers=editor
        )
    ).status_code == 422

    # New interviews use the new settings; the snapshot keeps old ones intact.
    seeker = await login("candidate@example.com")
    created = await new_interview(client, seeker, type_key="behavioral")
    assert created["interview"]["duration_minutes"] == 20
    assert created["interview"]["total_questions"] == 3
    listing = (await client.get("/api/v1/admin/interviews", headers=editor)).json()
    assert listing["total"] == 1
    assert listing["items"][0]["user_email"] == "candidate@example.com"


async def test_admin_versions_and_tests_prompts(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    admin = await login(ROOT_ADMIN_EMAIL)
    prompts = (await client.get("/api/v1/admin/prompts", headers=admin)).json()
    by_name = {p["name"]: p for p in prompts}
    assert by_name["resume_parse"]["versions"] == 2
    assert by_name["resume_parse"]["active_version"] == 2
    assert by_name["interviewer"]["active_version"] == 1

    detail = (await client.get("/api/v1/admin/prompts/interviewer", headers=admin)).json()
    assert "question" in detail["variables"]
    assert "fence" not in detail["variables"]
    original = detail["versions"][0]

    unknown = await client.post(
        "/api/v1/admin/prompts/interviewer/versions",
        json={"system": "Hello {{ secret_env }}", "user": original["user"]},
        headers=admin,
    )
    assert unknown.status_code == 400
    assert "secret_env" in unknown.json()["error"]["details"][0]
    broken = await client.post(
        "/api/v1/admin/prompts/interviewer/versions",
        json={"system": "{% if %}", "user": ""},
        headers=admin,
    )
    assert broken.json()["error"]["code"] == "invalid_template"

    edited = original["system"] + "\nAlways be kind."
    created = await client.post(
        "/api/v1/admin/prompts/interviewer/versions",
        json={"system": edited, "user": original["user"], "notes": "kinder", "activate": True},
        headers=admin,
    )
    assert created.status_code == 201, created.text
    assert created.json()["active_version"] == 2
    assert created.json()["versions"][0]["created_by_email"] == ROOT_ADMIN_EMAIL

    # Production calls now render the new version.
    messages, label = await prompt_store.render("interviewer", **_sample("interviewer"))
    assert label == "interviewer@v2"
    assert messages[0].content.endswith("Always be kind.")

    rolled = await client.post(
        "/api/v1/admin/prompts/interviewer/activate", json={"version": 1}, headers=admin
    )
    assert rolled.json()["active_version"] == 1
    assert (await prompt_store.render("interviewer", **_sample("interviewer")))[
        1
    ] == "interviewer@v1"
    actions = list(
        await session.scalars(
            select(AuditLog.action).where(AuditLog.target_type == "prompt_template")
        )
    )
    assert sorted(actions) == ["prompt.activated", "prompt.version_created"]

    tested = await client.post(
        "/api/v1/admin/prompts/interviewer/test", json={"version": 2}, headers=admin
    )
    assert tested.status_code == 200, tested.text
    assert tested.json()["provider"] == "mock"
    assert tested.json()["messages"][0]["role"] == "system"
    draft = await client.post(
        "/api/v1/admin/prompts/interview_hint/test",
        json={"system": "Hint for {{ question }}", "user": "Go"},
        headers=admin,
    )
    assert draft.json()["messages"][0]["content"].startswith("Hint for Find the longest")
    prompt_entries = await session.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.target_type == "prompt_template")
    )
    assert prompt_entries == 2  # playground runs change nothing


def _sample(name: str) -> dict[str, Any]:
    from app.llm.prompt_samples import SAMPLES

    return SAMPLES[name]


def test_admin_templates_run_in_a_sandbox() -> None:
    from jinja2.exceptions import SecurityError, UndefinedError

    assert prompt_store.validate("interviewer", "{{ question.__class__ }}", "") == []
    with pytest.raises((SecurityError, UndefinedError)):
        prompt_store.render_text("{{ question.__class__.__mro__ }}", "", question="q")
