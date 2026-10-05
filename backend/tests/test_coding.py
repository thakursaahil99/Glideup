"""Coding practice: sandbox adapters, grading, problems API, submissions and the
question bank / AI generation admin."""

import json
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, Language, Question, QuestionStatus, TestCase, Verdict
from app.modules.coding.grading import grade, normalize
from app.modules.coding.runner import (
    FakeRunner,
    Judge0Runner,
    PistonRunner,
    RunRequest,
    piston_result,
)
from app.modules.coding.service import seed_problems
from app.workers.runtime import drain_inline_jobs
from tests.conftest import ROOT_ADMIN_EMAIL, LoginFn, UseSettings

REQ = RunRequest("python", "print(1)", "", 2.0, 256)


@pytest.fixture(autouse=True)
def programs() -> Iterator[None]:
    FakeRunner.programs.update(
        {
            "reverse": lambda s: " ".join(reversed(s.split())) + "\n",
            "sum": lambda s: f"{sum(map(int, s.split()[1:]))}\n",
            "double": lambda s: f"{2 * int(s.split()[0])}\n",
        }
    )
    yield
    FakeRunner.programs.clear()


# --- sandbox adapters ---


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({"run": {"stdout": "1\n", "code": 0, "cpu_time": 12, "memory": 2048000}}, "ok"),
        ({"compile": {"code": 1, "output": "error"}, "run": {}}, "compile_error"),
        ({"run": {"code": 1, "status": "RE", "stderr": "boom"}}, "runtime_error"),
        ({"run": {"code": None, "status": "TO"}}, "time_limit"),
        ({"run": {"signal": "SIGKILL", "status": "SG"}}, "memory_limit"),
        ({"run": {"status": "XX"}}, "sandbox_error"),
    ],
)
def test_piston_results_map_to_verdicts(payload: dict[str, Any], status: str) -> None:
    result = piston_result(payload)
    assert result.status == status
    if status == "ok":
        assert (result.stdout, result.time_ms, result.memory_kb) == ("1\n", 12, 2000)


async def test_piston_request_and_outage() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"run": {"stdout": "ok\n", "code": 0}})

    runner = PistonRunner(
        "http://piston", httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    assert (await runner.run(RunRequest("cpp", "int main(){}", "5", 2.0, 128))).stdout == "ok\n"
    assert seen["language"] == "c++"
    assert seen["files"][0]["name"] == "main.cpp"
    assert seen["run_timeout"] == 2000
    assert seen["run_memory_limit"] == 128 * 1024 * 1024

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    dead = PistonRunner("http://piston", httpx.AsyncClient(transport=httpx.MockTransport(down)))
    assert (await dead.run(REQ)).status == "sandbox_error"


@pytest.mark.parametrize(
    ("status_id", "status"),
    [
        (3, "ok"),
        (5, "time_limit"),
        (6, "compile_error"),
        (11, "runtime_error"),
        (13, "sandbox_error"),
    ],
)
async def test_judge0_statuses(status_id: int, status: str) -> None:
    import base64

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["enable_network"] is False
        assert body["language_id"] == 71
        return httpx.Response(
            201,
            json={
                "status": {"id": status_id},
                "stdout": base64.b64encode(b"42\n").decode(),
                "time": "0.05",
            },
        )

    runner = Judge0Runner(
        "http://judge0", "secret", httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    result = await runner.run(REQ)
    assert result.status == status
    assert result.stdout == "42\n"
    assert result.time_ms == 50


# --- grading ---


def test_output_comparison_ignores_trailing_whitespace() -> None:
    assert normalize("1 2  \n3\n\n\n") == normalize("1 2\n3")
    assert normalize("1 2") != normalize("1  2")


def _tests() -> list[TestCase]:
    return [
        TestCase(position=0, input="2\n", expected_output="4\n", hidden=False),
        TestCase(position=1, input="5\n", expected_output="10\n", hidden=True),
        TestCase(position=2, input="7\n", expected_output="14\n", hidden=True),
    ]


async def test_grading_verdicts_and_hidden_details() -> None:
    python = Language(key="python", name="Python", time_limit_s=2, memory_limit_mb=256)
    accepted = await grade(python, "# fake:double", _tests())
    assert (accepted.verdict, accepted.passed, accepted.total) == (Verdict.ACCEPTED, 3, 3)
    assert "input" in accepted.results[0]
    assert "input" not in accepted.results[1]  # hidden tests never reveal data
    assert "stdout" not in accepted.results[1]

    wrong = await grade(python, "print('echo')", _tests())  # echoes stdin
    assert wrong.verdict == Verdict.WRONG_ANSWER
    assert wrong.passed == 0

    broken = await grade(python, "COMPILE_ERROR", _tests())
    assert broken.verdict == Verdict.COMPILE_ERROR
    assert len(broken.results) == 1  # stopped after the first test
    assert broken.compile_output

    assert (await grade(python, "TIMEOUT", _tests())).verdict == Verdict.TIME_LIMIT
    assert (await grade(python, "CRASH", _tests())).verdict == Verdict.RUNTIME_ERROR


# --- problems API ---


async def test_seed_is_published_and_idempotent(session: AsyncSession) -> None:
    assert await seed_problems(session) == 8
    await session.commit()
    assert await seed_problems(session) == 0
    questions = list(await session.scalars(select(Question)))
    assert all(q.status == QuestionStatus.PUBLISHED for q in questions)
    for q in questions:
        assert any(not t.hidden for t in q.tests)
        assert sum(t.hidden for t in q.tests) >= 2
        assert q.templates
        assert q.templates[0].reference_solution


@pytest.fixture
async def seeded(session: AsyncSession) -> None:
    await seed_problems(session)
    await session.commit()


async def test_browse_and_solve(client: AsyncClient, login: LoginFn, seeded: None) -> None:
    headers = await login("coder@example.com")
    problems = (await client.get("/api/v1/problems", headers=headers)).json()
    assert len(problems) == 8
    assert {p["slug"] for p in problems} >= {"two-sum", "reverse-words", "edit-distance"}
    easy = (
        await client.get("/api/v1/problems", params={"difficulty": "easy"}, headers=headers)
    ).json()
    assert {p["difficulty"] for p in easy} == {"easy"}

    detail = (await client.get("/api/v1/problems/reverse-words", headers=headers)).json()
    assert set(detail["starters"]) == {"python", "javascript", "typescript", "java", "cpp", "go"}
    assert len(detail["examples"]) == 2
    assert detail["hidden_tests"] == 3
    assert "public class Main" in detail["starters"]["java"]

    ran = await client.post(
        "/api/v1/problems/reverse-words/run",
        json={"language": "go", "code": "// fake:reverse"},
        headers=headers,
    )
    assert ran.status_code == 200, ran.text
    assert ran.json()["verdict"] == "accepted"
    assert ran.json()["total"] == 2  # examples only

    body = {"language": "java", "code": "// fake:reverse"}
    first = await client.post(
        "/api/v1/problems/reverse-words/submissions",
        json=body,
        headers={**headers, "Idempotency-Key": "k1"},
    )
    assert first.status_code == 202
    again = await client.post(
        "/api/v1/problems/reverse-words/submissions",
        json=body,
        headers={**headers, "Idempotency-Key": "k1"},
    )
    assert again.json()["id"] == first.json()["id"]
    await drain_inline_jobs()
    result = (await client.get(f"/api/v1/submissions/{first.json()['id']}", headers=headers)).json()
    assert (result["verdict"], result["passed"], result["total"]) == ("accepted", 5, 5)
    assert result["code"] == "// fake:reverse"

    wrong = await client.post(
        "/api/v1/problems/two-sum/submissions",
        json={"language": "cpp", "code": "int main(){}"},
        headers=headers,
    )
    await drain_inline_jobs()
    graded = (await client.get(f"/api/v1/submissions/{wrong.json()['id']}", headers=headers)).json()
    assert graded["verdict"] == "wrong_answer"
    hidden = [r for r in graded["results"] if r["hidden"]]
    assert hidden
    assert all(r["input"] is None and r["stdout"] is None for r in hidden)

    listing = {p["slug"]: p for p in (await client.get("/api/v1/problems", headers=headers)).json()}
    assert listing["reverse-words"]["solved"] is True
    assert listing["two-sum"] == {**listing["two-sum"], "solved": False, "attempted": True}

    stranger = await login("other@example.com")
    assert (
        await client.get(f"/api/v1/submissions/{first.json()['id']}", headers=stranger)
    ).status_code == 404
    bad = await client.post(
        "/api/v1/problems/two-sum/run", json={"language": "cobol", "code": "x"}, headers=headers
    )
    assert bad.json()["error"]["code"] == "invalid_language"


async def test_submission_rate_limit(
    client: AsyncClient, login: LoginFn, seeded: None, use_settings: UseSettings
) -> None:
    headers = await login("coder@example.com")
    use_settings(submissions_per_minute=2)
    body = {"language": "python", "code": "x"}
    for _ in range(2):
        assert (
            await client.post("/api/v1/problems/two-sum/submissions", json=body, headers=headers)
        ).status_code == 202
    limited = await client.post("/api/v1/problems/two-sum/submissions", json=body, headers=headers)
    assert limited.status_code == 429


# --- admin ---


NEW_QUESTION = {
    "slug": "double-it",
    "title": "Double It",
    "difficulty": "easy",
    "topics": ["Math"],
    "statement": "Read n and print 2n.",
    "templates": [
        {"language_key": "python", "starter_code": "", "reference_solution": "# fake:double"}
    ],
    "tests": [
        {"input": "2\n", "expected_output": "4\n", "hidden": False},
        {"input": "-3\n", "expected_output": "-6\n", "hidden": True},
    ],
}


async def test_question_bank_lifecycle(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    from app.core.rbac import Role

    support = await login("helper@example.com", Role.SUPPORT)
    assert (await client.get("/api/v1/admin/questions", headers=support)).status_code == 403
    editor = await login("editor@example.com", Role.CONTENT_EDITOR)

    created = await client.post("/api/v1/admin/questions", json=NEW_QUESTION, headers=editor)
    assert created.status_code == 201, created.text
    qid = created.json()["id"]
    assert created.json()["topics"] == ["math"]
    assert created.json()["status"] == "draft"

    blocked = await client.patch(
        f"/api/v1/admin/questions/{qid}/status", json={"status": "published"}, headers=editor
    )
    assert blocked.json()["error"]["code"] == "not_validated"

    validated = (
        await client.post(f"/api/v1/admin/questions/{qid}/validate", headers=editor)
    ).json()
    assert validated["validation"]["ok"] is True
    assert validated["validation"]["details"][0]["verdict"] == "accepted"
    published = await client.patch(
        f"/api/v1/admin/questions/{qid}/status", json={"status": "published"}, headers=editor
    )
    assert published.json()["status"] == "published"

    seeker = await login("coder@example.com")
    assert (await client.get("/api/v1/problems/double-it", headers=seeker)).status_code == 200

    # A wrong expected output fails validation; editing unpublishes until it's fixed.
    broken = {
        **NEW_QUESTION,
        "tests": [
            *NEW_QUESTION["tests"],
            {"input": "5\n", "expected_output": "11\n", "hidden": True},
        ],
    }
    edited = (
        await client.put(f"/api/v1/admin/questions/{qid}", json=broken, headers=editor)
    ).json()
    assert edited["status"] == "draft"
    assert edited["validation"] is None
    assert (await client.get("/api/v1/problems/double-it", headers=seeker)).status_code == 404
    failing = (await client.post(f"/api/v1/admin/questions/{qid}/validate", headers=editor)).json()
    assert failing["validation"]["ok"] is False
    assert failing["validation"]["details"][0]["verdict"] == "wrong_answer"

    clash = await client.post("/api/v1/admin/questions", json=NEW_QUESTION, headers=editor)
    assert clash.status_code == 409
    listing = (await client.get("/api/v1/admin/questions", headers=editor)).json()
    assert len(listing) == 9  # 8 seeded on first view + ours
    actions = set(
        await session.scalars(select(AuditLog.action).where(AuditLog.target_type == "question"))
    )
    assert actions >= {"question.created", "question.updated", "question.status_changed"}


async def test_languages_admin(client: AsyncClient, login: LoginFn, seeded: None) -> None:
    admin = await login(ROOT_ADMIN_EMAIL)
    updated = await client.patch(
        "/api/v1/admin/languages/go", json={"enabled": False, "time_limit_s": 1.5}, headers=admin
    )
    assert updated.json()["enabled"] is False
    seeker = await login("coder@example.com")
    detail = (await client.get("/api/v1/problems/two-sum", headers=seeker)).json()
    assert "go" not in detail["starters"]
    refused = await client.post(
        "/api/v1/problems/two-sum/run", json={"language": "go", "code": "x"}, headers=seeker
    )
    assert refused.status_code == 400


async def test_ai_generation_queue(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    admin = await login(ROOT_ADMIN_EMAIL)
    queued = await client.post(
        "/api/v1/admin/question-generation",
        json={"topic": "prefix sums", "difficulty": "easy", "count": 2},
        headers=admin,
    )
    assert queued.status_code == 202
    await drain_inline_jobs()
    items = (await client.get("/api/v1/admin/question-generation", headers=admin)).json()
    assert [i["status"] for i in items] == ["ready", "ready"]
    draft = items[0]["draft"]
    # Expected outputs came from running the reference, not from the model.
    assert [t["expected_output"] for t in draft["tests"]] == ["6\n", "-5\n", "100\n"]
    assert draft["tests"][0]["hidden"] is False

    approved = await client.post(
        f"/api/v1/admin/question-generation/{items[0]['id']}/review",
        json={"approve": True, "publish": True},
        headers=admin,
    )
    assert approved.json()["status"] == "approved"
    question = await session.get(Question, uuid.UUID(approved.json()["question_id"]))
    assert question is not None
    assert (question.status, question.source) == (QuestionStatus.PUBLISHED, "ai")
    assert len(question.templates) == 6

    rejected = await client.post(
        f"/api/v1/admin/question-generation/{items[1]['id']}/review",
        json={"approve": False, "note": "duplicate"},
        headers=admin,
    )
    assert rejected.json()["status"] == "rejected"
    again = await client.post(
        f"/api/v1/admin/question-generation/{items[1]['id']}/review",
        json={"approve": True},
        headers=admin,
    )
    assert again.status_code == 409
    total = await session.scalar(select(func.count()).select_from(Question))
    assert total == 1
