"""Application tracker, reminders, dashboard and user reports."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, Job, JobSource, Reminder
from app.modules.dashboard.service import next_step, streak
from app.modules.tracker import service as tracker
from tests.conftest import ROOT_ADMIN_EMAIL, LoginFn
from tests.test_jobs import FakePlugin, fake, fake_source, jobs_by_ext, posting  # noqa: F401


@pytest.fixture
async def job(session: AsyncSession, fake: FakePlugin, fake_source: JobSource) -> Job:  # noqa: F811
    from app.modules.jobs.ingestion import ingest_source
    from app.workers.runtime import drain_inline_jobs

    fake.scopes = {"fake:a": [posting("py", title="Backend Engineer", company="Acme")]}
    await ingest_source("fake")
    await drain_inline_jobs()
    return (await jobs_by_ext(session))["py"]


async def test_track_and_move_applications(client: AsyncClient, login: LoginFn, job: Job) -> None:
    headers = await login("seeker@example.com")
    tracked = await client.post(
        "/api/v1/applications", json={"job_id": str(job.id)}, headers=headers
    )
    assert tracked.status_code == 201
    app_ = tracked.json()
    assert (app_["company"], app_["title"], app_["status"]) == ("Acme", "Backend Engineer", "saved")
    assert app_["url"] == "https://careers.example.com/py"
    assert app_["applied_at"] is None
    dup = await client.post("/api/v1/applications", json={"job_id": str(job.id)}, headers=headers)
    assert dup.json()["error"]["code"] == "already_tracked"

    manual = await client.post(
        "/api/v1/applications",
        json={
            "company": "Globex",
            "title": "SRE",
            "url": "https://globex.example/jobs/1",
            "status": "applied",
        },
        headers=headers,
    )
    assert manual.json()["applied_at"] is not None
    missing = await client.post("/api/v1/applications", json={"company": "X"}, headers=headers)
    assert missing.json()["error"]["code"] == "details_required"

    moved = await client.patch(
        f"/api/v1/applications/{app_['id']}",
        json={"status": "applied", "position": 0, "note": "Referred by Priya"},
        headers=headers,
    )
    body = moved.json()
    assert body["status"] == "applied"
    assert body["applied_at"] is not None
    assert [e["kind"] for e in body["events"]] == ["created", "status", "note"]
    assert body["events"][1] == {
        **body["events"][1],
        "from_status": "saved",
        "to_status": "applied",
    }
    board = (await client.get("/api/v1/applications", headers=headers)).json()
    applied = sorted((a for a in board if a["status"] == "applied"), key=lambda a: a["position"])
    assert [a["company"] for a in applied] == ["Acme", "Globex"]  # inserted at the top

    stranger = await login("other@example.com")
    assert (
        await client.patch(
            f"/api/v1/applications/{app_['id']}", json={"status": "offer"}, headers=stranger
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/applications/{app_['id']}", headers=headers)
    ).status_code == 204
    assert len((await client.get("/api/v1/applications", headers=headers)).json()) == 1


async def test_reminders_are_emailed_once(
    client: AsyncClient, login: LoginFn, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[tuple[str, str]] = []

    async def fake_send(to: str, subject: str, body: str) -> bool:
        sent.append((to, subject))
        return True

    monkeypatch.setattr(tracker, "send_email", fake_send)
    headers = await login("seeker@example.com")
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    future = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    due = (
        await client.post(
            "/api/v1/reminders",
            json={"title": "Follow up with Acme", "due_at": past},
            headers=headers,
        )
    ).json()
    await client.post(
        "/api/v1/reminders", json={"title": "Prep", "due_at": future}, headers=headers
    )

    assert await tracker.send_due_reminders_job() == 1
    assert sent == [("seeker@example.com", "Reminder: Follow up with Acme")]
    assert await tracker.send_due_reminders_job() == 0  # never twice

    rescheduled = await client.patch(
        f"/api/v1/reminders/{due['id']}", json={"due_at": past}, headers=headers
    )
    assert rescheduled.status_code == 200
    assert await tracker.send_due_reminders_job() == 1  # rescheduling re-arms the email
    await client.patch(f"/api/v1/reminders/{due['id']}", json={"done": True}, headers=headers)
    open_ = (await client.get("/api/v1/reminders", headers=headers)).json()
    assert [r["title"] for r in open_] == ["Prep"]
    assert (
        len(
            (
                await client.get(
                    "/api/v1/reminders", params={"include_done": True}, headers=headers
                )
            ).json()
        )
        == 2
    )
    assert await session.scalar(select(Reminder.emailed_at).where(Reminder.title == "Prep")) is None


def test_streak_counts_consecutive_days() -> None:
    today = date(2026, 10, 5)
    days = {today, today - timedelta(days=1), today - timedelta(days=2), today - timedelta(days=4)}
    assert streak(days, today) == (3, True)
    assert streak(days - {today}, today) == (2, False)  # not practised yet today: streak kept
    assert streak({today - timedelta(days=3)}, today) == (0, False)


@pytest.mark.parametrize(
    ("kwargs", "href"),
    [
        ({"has_resume": False}, "/onboarding"),
        ({"reminders_due": 2}, "/tracker"),
        ({"applications": 0}, "/jobs/recommended"),
        ({"interviews": 0}, "/interviews"),
        ({"tests": 0}, "/tests"),
        ({"weakest": "System design"}, "/interviews"),
        ({}, "/tests"),
    ],
)
def test_next_step_rules(kwargs: dict[str, Any], href: str) -> None:
    base = {
        "has_resume": True,
        "applications": 2,
        "interviews": 1,
        "tests": 1,
        "reminders_due": 0,
        "weakest": None,
    }
    assert next_step(**{**base, **kwargs}).href == href


async def test_dashboard(client: AsyncClient, login: LoginFn, job: Job) -> None:
    headers = await login("seeker@example.com")
    empty = (await client.get("/api/v1/dashboard", headers=headers)).json()
    assert empty["next_step"]["href"] == "/onboarding"
    assert empty["streak_days"] == 0
    assert set(empty["applications"]) >= {"saved", "applied", "offer"}

    await client.post(
        "/api/v1/applications", json={"job_id": str(job.id), "status": "applied"}, headers=headers
    )
    await client.post(
        "/api/v1/reminders",
        json={"title": "Call back", "due_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
        headers=headers,
    )
    board = (await client.get("/api/v1/dashboard", headers=headers)).json()
    assert board["applications"]["applied"] == 1
    assert board["totals"]["applications"] == 1
    assert [r["title"] for r in board["reminders"]] == ["Call back"]


async def test_user_reports_queue(
    client: AsyncClient, login: LoginFn, session: AsyncSession, job: Job
) -> None:
    from app.core.rbac import Role

    headers = await login("seeker@example.com")
    created = await client.post(
        "/api/v1/reports",
        json={
            "kind": "broken_job_link",
            "message": "The apply link 404s.",
            "target_type": "job",
            "target_id": str(job.id),
            "page_url": f"/jobs/{job.id}",
        },
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json()["state"] == "open"

    seeker_admin = await client.get("/api/v1/admin/reports", headers=headers)
    assert seeker_admin.status_code == 403
    support = await login("helper@example.com", Role.SUPPORT)
    queue = (await client.get("/api/v1/admin/reports", headers=support)).json()
    assert queue["total"] == 1
    assert queue["items"][0]["user_email"] == "seeker@example.com"
    denied = await client.patch(
        f"/api/v1/admin/reports/{created.json()['id']}", json={"state": "resolved"}, headers=support
    )
    assert denied.status_code == 403  # support reads, admins act

    admin = await login(ROOT_ADMIN_EMAIL)
    handled = await client.patch(
        f"/api/v1/admin/reports/{created.json()['id']}",
        json={"state": "resolved", "reply": "Fixed, thanks!"},
        headers=admin,
    )
    assert handled.json()["state"] == "resolved"
    mine = (await client.get("/api/v1/reports", headers=headers)).json()
    assert mine[0]["reply"] == "Fixed, thanks!"
    assert (await client.get("/api/v1/admin/reports", headers=admin)).json()[
        "total"
    ] == 0  # open only
    assert await session.scalar(
        select(AuditLog.action).where(AuditLog.action == "user_report.handled")
    )
