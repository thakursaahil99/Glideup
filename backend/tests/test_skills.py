"""Framework tests, grading, skill scores and badges."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, FrameworkAttempt, Question, SkillScore, UserBadge
from app.modules.coding.runner import FakeRunner
from app.modules.coding.service import seed_problems
from app.modules.skills.content import public_content, validate_content
from app.modules.skills.grading import GradeDraft, Judgement, combine, level_for, score_items
from app.workers.runtime import drain_inline_jobs
from tests.conftest import ROOT_ADMIN_EMAIL, LoginFn, UseSettings

# --- content and grading rules ---


def test_content_is_validated() -> None:
    with pytest.raises(ValueError, match="index"):
        validate_content("mcq", {"options": ["a", "b"], "answer": 2})
    with pytest.raises(ValueError, match="pattern"):
        validate_content(
            "review",
            {
                "language": "python",
                "code": "x = 1  # short",
                "issues": [{"key": "Bad Key", "description": "nope"}],
            },
        )
    with pytest.raises(ValueError, match="regular expression"):
        validate_content(
            "project",
            {
                "language": "python",
                "requirements": [{"key": "ok", "description": "has x", "pattern": "("}],
            },
        )
    with pytest.raises(ValueError, match="Unknown question type"):
        validate_content("essay", {})


def test_public_content_hides_answers() -> None:
    mcq = validate_content("mcq", {"options": ["a", "b"], "answer": 1, "explanation": "because"})
    assert public_content("mcq", mcq) == {"options": ["a", "b"]}
    review = validate_content(
        "review",
        {
            "language": "python",
            "code": "print('hello world')",
            "issues": [{"key": "secret", "description": "the planted bug"}],
        },
    )
    assert "issues" not in public_content("review", review)
    project = validate_content(
        "project",
        {
            "language": "python",
            "requirements": [
                {"key": "pydantic", "description": "Uses Pydantic", "pattern": "BaseModel"}
            ],
        },
    )
    assert public_content("project", project)["requirements"] == ["Uses Pydantic"]  # no pattern
    assert public_content("viva", {"key_points": ["x", "y"]}) == {}


def test_item_scoring_and_static_checks() -> None:
    rubric = [
        {"key": "models", "description": "Pydantic models", "pattern": "BaseModel", "weight": 2},
        {"key": "status", "description": "Returns 201", "pattern": "201", "weight": 1},
        {"key": "partial", "description": "PATCH is partial", "weight": 1},
    ]
    draft = GradeDraft(
        items=[
            Judgement(key="models", met="no"),
            Judgement(key="status", met="yes"),
            Judgement(key="partial", met="partial"),
        ]
    )
    # BaseModel is present: at least half credit even though the model said "no";
    # 201 is absent: zero even though the model said "yes".
    score, items = score_items("project", rubric, draft, "class Todo(BaseModel): ...")
    assert [i["credit"] for i in items] == [0.5, 0.0, 0.5]
    assert score == round((2 * 0.5 + 0 + 0.5) / 4, 3)


def test_section_weights_and_levels() -> None:
    overall, sections = combine(
        {"mcq": [1, 1, 0, 1], "review": [0.5], "viva": [1, 0.5], "project": [0.25]}
    )
    assert sections == {"mcq": 75, "review": 50, "viva": 75, "project": 25}
    assert overall == round(0.3 * 75 + 0.2 * 50 + 0.2 * 75 + 0.3 * 25)
    assert combine({"mcq": [1.0]})[0] == 100  # missing sections don't drag the score down
    assert [level_for(s) for s in (90, 65, 45, 10)] == [
        "expert",
        "advanced",
        "intermediate",
        "beginner",
    ]


# --- the test flow ---


def _answers(attempt: dict[str, Any], session_questions: dict[str, Question]) -> dict[str, Any]:
    """Correct MCQs, and open answers that mention every rubric item."""
    out: dict[str, Any] = {}
    for q in attempt["questions"]:
        stored = session_questions[q["id"]]
        content = stored.content or {}
        if q["type"] == "mcq":
            out[q["id"]] = content["answer"]
        elif q["type"] == "review":
            out[q["id"]] = "\n".join(i["description"] for i in content["issues"])
        elif q["type"] == "viva":
            out[q["id"]] = "\n".join(content["key_points"])
        else:
            out[q["id"]] = (
                "\n".join(
                    f"{r['description']} {r.get('pattern') or ''}" for r in content["requirements"]
                )
                + "\nBaseModel min_length 201 HTTPException todo_id: int"
                + " useState toLowerCase key={item.id} No results"
            )
    return out


async def test_take_and_pass_a_react_test(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    headers = await login("dev@example.com")
    frameworks = (await client.get("/api/v1/frameworks", headers=headers)).json()
    assert {f["key"] for f in frameworks} == {"react", "fastapi"}
    assert all(f["questions"] == 13 and f["best_score"] is None for f in frameworks)

    started = await client.post("/api/v1/frameworks/react/attempts", headers=headers)
    assert started.status_code == 201
    attempt = started.json()
    types = [q["type"] for q in attempt["questions"]]
    assert sorted(types) == sorted(["mcq"] * 6 + ["review", "viva", "viva", "project"])
    for q in attempt["questions"]:  # nothing that gives the answer away
        assert "answer" not in q["content"]
        assert "issues" not in q["content"]
        assert "key_points" not in q["content"]
    resumed = (await client.post("/api/v1/frameworks/react/attempts", headers=headers)).json()
    assert resumed["id"] == attempt["id"]

    stored = {str(q.id): q for q in await session.scalars(select(Question))}
    answers = _answers(attempt, stored)
    bad = await client.put(
        f"/api/v1/framework-attempts/{attempt['id']}/answers",
        json={"answers": {str(uuid.uuid4()): 1}},
        headers=headers,
    )
    assert bad.json()["error"]["code"] == "unknown_question"
    saved = await client.put(
        f"/api/v1/framework-attempts/{attempt['id']}/answers",
        json={"answers": answers},
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json()["answers"] == answers

    submitted = await client.post(
        f"/api/v1/framework-attempts/{attempt['id']}/submit", headers=headers
    )
    assert submitted.status_code == 202
    await drain_inline_jobs()
    graded = (
        await client.get(f"/api/v1/framework-attempts/{attempt['id']}", headers=headers)
    ).json()
    assert graded["status"] == "graded"
    assert graded["sections"]["mcq"] == 100
    assert graded["score"] >= 60
    assert graded["level"] in ("advanced", "expert")
    mcq = next(q for q in graded["questions"] if q["type"] == "mcq")
    assert "answer" in mcq["content"]  # revealed after grading
    assert mcq["result"]["score"] == 1.0

    skills = (await client.get("/api/v1/me/skills", headers=headers)).json()
    assert skills["skills"][0]["skill"] == "react"
    assert skills["skills"][0]["score"] == graded["score"]
    assert "react-practitioner" in {b["key"] for b in skills["badges"]}
    best = {
        f["key"]: f["best_score"]
        for f in (await client.get("/api/v1/frameworks", headers=headers)).json()
    }
    assert best["react"] == graded["score"]

    # Submitting again is harmless.
    again = await client.post(f"/api/v1/framework-attempts/{attempt['id']}/submit", headers=headers)
    assert again.json()["status"] == "graded"


async def test_empty_answers_score_zero_and_time_limit(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    headers = await login("dev@example.com")
    attempt = (await client.post("/api/v1/frameworks/fastapi/attempts", headers=headers)).json()
    row = await session.get(FrameworkAttempt, uuid.UUID(attempt["id"]))
    assert row is not None
    row.ends_at = datetime.now(UTC) - timedelta(minutes=10)
    await session.commit()
    late = await client.put(
        f"/api/v1/framework-attempts/{attempt['id']}/answers",
        json={"answers": {attempt["questions"][0]["id"]: 0}},
        headers=headers,
    )
    assert late.json()["error"]["code"] == "time_up"
    await client.post(f"/api/v1/framework-attempts/{attempt['id']}/submit", headers=headers)
    await drain_inline_jobs()
    graded = (
        await client.get(f"/api/v1/framework-attempts/{attempt['id']}", headers=headers)
    ).json()
    assert graded["score"] == 0
    assert graded["level"] == "beginner"
    stranger = await login("other@example.com")
    assert (
        await client.get(f"/api/v1/framework-attempts/{attempt['id']}", headers=stranger)
    ).status_code == 404


async def test_grading_outage_can_be_retried(
    client: AsyncClient, login: LoginFn, use_settings: UseSettings
) -> None:
    headers = await login("dev@example.com")
    attempt = (await client.post("/api/v1/frameworks/react/attempts", headers=headers)).json()
    open_q = next(q for q in attempt["questions"] if q["type"] == "viva")
    await client.put(
        f"/api/v1/framework-attempts/{attempt['id']}/answers",
        json={"answers": {open_q["id"]: "Some answer"}},
        headers=headers,
    )
    from app.llm.factory import set_gateway

    use_settings(
        llm_routes={"framework_grade": ["ollama:none"]},
        llm_allow_mock_fallback=False,
        ollama_base_url="http://127.0.0.1:9",
    )
    set_gateway(None)
    await client.post(f"/api/v1/framework-attempts/{attempt['id']}/submit", headers=headers)
    await drain_inline_jobs()
    failed = (
        await client.get(f"/api/v1/framework-attempts/{attempt['id']}", headers=headers)
    ).json()
    assert failed["status"] == "failed"
    assert failed["error"]

    use_settings(llm_routes={"framework_grade": ["mock:mock-1"]})
    set_gateway(None)
    await client.post(f"/api/v1/framework-attempts/{attempt['id']}/submit", headers=headers)
    await drain_inline_jobs()
    assert (
        await client.get(f"/api/v1/framework-attempts/{attempt['id']}", headers=headers)
    ).json()["status"] == "graded"


async def test_coding_skill_and_badges(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    FakeRunner.programs["reverse"] = lambda s: " ".join(reversed(s.split())) + "\n"
    try:
        await seed_problems(session)
        await session.commit()
        headers = await login("dev@example.com")
        response = await client.post(
            "/api/v1/problems/reverse-words/submissions",
            json={"language": "go", "code": "// fake:reverse"},
            headers=headers,
        )
        assert response.status_code == 202
        await drain_inline_jobs()
    finally:
        FakeRunner.programs.clear()
    skills = (await client.get("/api/v1/me/skills", headers=headers)).json()
    assert skills["skills"] == [
        {**skills["skills"][0], "skill": "go", "kind": "language", "score": 10, "level": "beginner"}
    ]
    assert [b["key"] for b in skills["badges"]] == ["first-accepted"]
    badge_rows = list(await session.scalars(select(UserBadge)))
    assert len(badge_rows) == 1
    assert await session.get(SkillScore, (badge_rows[0].user_id, "go")) is not None


async def test_admin_frameworks_and_framework_questions(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    admin = await login(ROOT_ADMIN_EMAIL)
    frameworks = (await client.get("/api/v1/admin/frameworks", headers=admin)).json()
    assert {f["key"] for f in frameworks} == {"react", "fastapi"}
    bad = await client.patch(
        "/api/v1/admin/frameworks/react", json={"composition": {"essay": 2}}, headers=admin
    )
    assert bad.status_code == 422
    updated = await client.patch(
        "/api/v1/admin/frameworks/react",
        json={"composition": {"mcq": 3, "viva": 1}, "duration_minutes": 20},
        headers=admin,
    )
    assert updated.json()["composition"] == {"mcq": 3, "viva": 1}
    assert await session.scalar(
        select(AuditLog.action).where(AuditLog.action == "framework.updated")
    )

    question = {
        "type": "mcq",
        "framework_key": "react",
        "slug": "react-mcq-new",
        "title": "New MCQ",
        "difficulty": "easy",
        "statement": "Which hook stores state?",
        "content": {"options": ["useRef", "useState"], "answer": 1},
    }
    created = await client.post("/api/v1/admin/questions", json=question, headers=admin)
    assert created.status_code == 201, created.text
    assert created.json()["type"] == "mcq"
    invalid = await client.post(
        "/api/v1/admin/questions",
        json={**question, "slug": "react-mcq-bad", "content": {"options": ["a"], "answer": 3}},
        headers=admin,
    )
    assert invalid.json()["error"]["code"] == "invalid_content"
    no_fw = await client.post(
        "/api/v1/admin/questions",
        json={**question, "slug": "react-mcq-nofw", "framework_key": None},
        headers=admin,
    )
    assert no_fw.json()["error"]["code"] == "framework_required"
    validated = (
        await client.post(f"/api/v1/admin/questions/{created.json()['id']}/validate", headers=admin)
    ).json()
    assert validated["validation"]["ok"] is True

    seeker = await login("dev@example.com")
    attempt = (await client.post("/api/v1/frameworks/react/attempts", headers=seeker)).json()
    assert sorted(q["type"] for q in attempt["questions"]) == ["mcq", "mcq", "mcq", "viva"]
    problems = (await client.get("/api/v1/problems", headers=seeker)).json()
    assert all(
        not p["slug"].startswith("react-") for p in problems
    )  # framework questions aren't problems
