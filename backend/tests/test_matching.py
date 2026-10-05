"""Matching: score maths, grounding, job embeddings, the match / analysis /
recommendation APIs and the admin embedding controls."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, ExperienceLevel, Job, JobMatch, JobSource, Profile, Resume
from app.modules.matching import embeddings
from app.modules.matching.embeddings import embed_pending_jobs, job_document_text
from app.modules.matching.schemas import MissingSkill, SkillGapAnalysis, WeakSkill, ground
from app.modules.matching.scoring import (
    level_fit,
    match_label,
    score_match,
    semantic_score,
    skill_overlap,
)
from app.modules.matching.service import role_title
from app.workers.runtime import drain_inline_jobs
from tests.conftest import ROOT_ADMIN_EMAIL, SAMPLE_RESUME_LINES, LoginFn, UseSettings, make_pdf
from tests.test_jobs import FakePlugin, fake, fake_source, jobs_by_ext, posting  # noqa: F401
from tests.test_resumes import upload_and_parse

HAVE = {"python": "Python", "fastapi": "FastAPI", "postgresql": "PostgreSQL", "docker": "Docker"}

# --- scoring maths ---


def test_skill_overlap_splits_matched_transferable_and_missing() -> None:
    matched, transferable, missing = skill_overlap(
        ["python", "MySQL", "Terraform", "Python", "Postgres"], HAVE
    )
    assert matched == ["Python", "PostgreSQL"]  # aliases and duplicates collapse
    assert [(t.skill, t.via) for t in transferable] == [("MySQL", "PostgreSQL")]
    assert missing == ["Terraform"]


@pytest.mark.parametrize(
    ("level", "years", "expected"),
    [
        (ExperienceLevel.SENIOR, 7, 1.0),
        (ExperienceLevel.SENIOR, 3, 0.5),  # two years short
        (ExperienceLevel.SENIOR, 0, 0.0),
        (ExperienceLevel.ENTRY, 4, 0.8),  # over-qualified: milder
        (ExperienceLevel.ENTRY, 30, 0.4),  # ...with a floor
        (ExperienceLevel.UNKNOWN, 5, None),
        (ExperienceLevel.MID, None, None),
    ],
)
def test_level_fit(level: ExperienceLevel, years: float | None, expected: float | None) -> None:
    fit = level_fit(level, years)
    if expected is None:
        assert fit is None
    else:
        assert fit == pytest.approx(expected)


def test_semantic_score_is_clamped_to_the_calibrated_range() -> None:
    assert semantic_score(0.10) == 0.0
    assert semantic_score(0.99) == 1.0
    assert 0 < semantic_score(0.6) < 1


def test_score_combines_available_signals() -> None:
    full = score_match(
        similarity=0.78,
        job_skills=["Python", "FastAPI", "PostgreSQL"],
        have=HAVE,
        level=ExperienceLevel.SENIOR,
        years=6,
    )
    assert full is not None
    assert full.score == 100
    assert full.label == "Strong match"
    assert not full.partial

    # No embeddings yet: skills + level only, flagged partial.
    partial = score_match(
        similarity=None,
        job_skills=["Python", "Go"],
        have=HAVE,
        level=ExperienceLevel.UNKNOWN,
        years=None,
    )
    assert partial is not None
    assert partial.partial
    assert partial.score == 50

    # A job that names one skill barely moves the score through skills alone.
    one_skill = score_match(
        similarity=0.40, job_skills=["Python"], have=HAVE, level=ExperienceLevel.UNKNOWN, years=None
    )
    assert one_skill is not None
    assert one_skill.score == round(100 * (0.4 / 3) / (0.6 + 0.4 / 3))

    # Level only ever lowers a score: a fresher for a senior role keeps 70% of the fit.
    fresher = score_match(
        similarity=0.78,
        job_skills=["Python", "FastAPI", "PostgreSQL"],
        have=HAVE,
        level=ExperienceLevel.SENIOR,
        years=0,
    )
    assert fresher is not None
    assert fresher.score == 70
    assert fresher.level == 0.0

    # Nothing to judge on.
    assert (
        score_match(
            similarity=None, job_skills=[], have=HAVE, level=ExperienceLevel.SENIOR, years=5
        )
        is None
    )


@pytest.mark.parametrize(
    ("title", "role"),
    [
        (
            "Forward Deployed Engineer - Software Engineer - United Kingdom",
            "forward deployed engineer - software engineer",
        ),
        ("Backend Engineer (Bengaluru)", "backend engineer"),
        ("Engineer, Remote", "engineer"),
        ("Software Engineer - Payments", "software engineer - payments"),  # a team, not a place
        ("Engineer - Go", "engineer - go"),
    ],
)
def test_role_title_drops_trailing_locations(title: str, role: str) -> None:
    assert role_title(title) == role


def test_match_labels() -> None:
    assert [match_label(s) for s in (90, 75, 60, 40, 10)] == [
        "Strong match",
        "Strong match",
        "Good match",
        "Fair match",
        "Low match",
    ]


# --- grounding the LLM's answer ---


def test_ground_drops_unsupported_claims() -> None:
    analysis = SkillGapAnalysis(
        summary="Decent fit.",
        missing=[
            MissingSkill(skill="k8s", importance="nice to have"),  # alias of a posted skill
            MissingSkill(skill="Rust"),  # not in the posting: invented
            MissingSkill(skill="Python"),  # the candidate has it
            MissingSkill(skill="Kubernetes"),  # duplicate of the first
        ],
        weak=[WeakSkill(skill="Docker"), WeakSkill(skill="Scala")],  # Scala: not theirs
    )
    grounded = ground(
        analysis,
        job_text="We run Python services on Kubernetes and Docker.",
        job_skills=["Python", "Kubernetes", "Docker"],
        candidate_skills={"python", "docker"},
    )
    assert [(m.skill, m.importance) for m in grounded.missing] == [("Kubernetes", "preferred")]
    assert [w.skill for w in grounded.weak] == ["Docker"]


def test_job_document_text_is_prefixed_and_bounded() -> None:
    text = job_document_text("SRE", "Acme", ExperienceLevel.SENIOR, ["Go"], "x" * 5000)
    assert text.startswith(embeddings.DOCUMENT_PREFIX + "SRE at Acme\nLevel: senior\nSkills: Go")
    assert len(text) < 1700
    assert "Level" not in job_document_text("SRE", "Acme", ExperienceLevel.UNKNOWN, [], "")


# --- end to end ---


@pytest.fixture
async def market(session: AsyncSession, fake: FakePlugin, fake_source: JobSource) -> dict[str, Job]:  # noqa: F811
    from app.modules.jobs.ingestion import ingest_source

    fake.scopes = {
        "fake:a": [
            posting("py", title="Senior Backend Engineer",
                    body="<p>Python, FastAPI, PostgreSQL, Docker, Kubernetes and Terraform.</p>"),
            posting("java", title="Java Developer", company="Beta",
                    body="<p>Java, Spring Boot and MySQL.</p>"),
            posting("fe", title="Frontend Engineer", company="Gamma", location="Remote",
                    body="<p>React, TypeScript and Next.js.</p>"),
            posting("sales", title="Account Executive", company="Delta",
                    body="<p>Close enterprise deals.</p>"),
        ]
    }  # fmt: skip
    await ingest_source("fake")
    await drain_inline_jobs()  # ingestion queues the embedding backfill
    return await jobs_by_ext(session)


async def seeker(client: AsyncClient, login: LoginFn) -> dict[str, str]:
    headers = await login("asha@example.com")
    resume = await upload_and_parse(client, headers, make_pdf(SAMPLE_RESUME_LINES))
    assert resume["status"] == "parsed"
    return headers


async def test_ingestion_embeds_listed_jobs(session: AsyncSession, market: dict[str, Job]) -> None:
    key = embeddings.current_key()
    assert key == "mock:mock-1#t1"
    rows = (
        await session.execute(select(Job.embedding_model, Job.embedded_hash, Job.content_hash))
    ).all()
    assert len(rows) == 4
    assert all(model == key and embedded == content for model, embedded, content in rows)
    assert (await embed_pending_jobs()).embedded == 0  # nothing left to do

    # An edited posting is re-embedded.
    job = market["py"]
    job.content_hash = "changed"
    await session.commit()
    assert await embeddings.count_pending(session) == 1
    assert (await embed_pending_jobs()).embedded == 1


async def test_job_cards_carry_a_match_score(
    client: AsyncClient, login: LoginFn, market: dict[str, Job]
) -> None:
    anonymous_ish = await login("new@example.com")  # no resume: no scores
    listing = (await client.get("/api/v1/jobs", headers=anonymous_ish)).json()
    assert all(item["match"] is None for item in listing["items"])

    headers = await seeker(client, login)
    listing = (await client.get("/api/v1/jobs", headers=headers)).json()
    scores = {item["title"]: item["match"] for item in listing["items"]}
    backend = scores["Senior Backend Engineer"]
    assert backend["partial"] is False
    assert backend["matched_skills"] == 5
    assert backend["total_skills"] == 6
    assert backend["score"] > scores["Frontend Engineer"]["score"]
    # (Absolute values depend on the embedding model; quality is measured by the eval
    # in app/llm/evals/match.py, not by the mock's hashed vectors.)

    detail = (await client.get(f"/api/v1/jobs/{market['py'].id}", headers=headers)).json()
    assert detail["match"]["score"] == backend["score"]


async def test_match_detail_explains_the_score(
    client: AsyncClient, login: LoginFn, market: dict[str, Job]
) -> None:
    headers = await seeker(client, login)
    body = (await client.get(f"/api/v1/jobs/{market['java'].id}/match", headers=headers)).json()
    assert body["available"] is True
    assert body["transferable"] == [{"skill": "MySQL", "via": "PostgreSQL"}]
    assert set(body["missing"]) == {"Java", "Spring Boot"}
    assert body["practice"] == {"languages": ["Java"], "frameworks": ["Spring Boot"]}
    assert set(body["parts"]) == {"semantic", "skills", "level"}
    assert body["analysis"] is None

    py = (await client.get(f"/api/v1/jobs/{market['py'].id}/match", headers=headers)).json()
    assert {m["name"] for m in py["matched"]} >= {"Python", "FastAPI", "PostgreSQL"}
    assert all("resume" in m["sources"] for m in py["matched"])
    assert py["missing"] == ["Terraform"]


async def test_ai_skill_gap_analysis(
    client: AsyncClient, login: LoginFn, market: dict[str, Job], session: AsyncSession
) -> None:
    headers = await seeker(client, login)
    url = f"/api/v1/jobs/{market['py'].id}/match"
    started = await client.post(f"{url}/analysis", headers=headers)
    assert started.status_code == 202
    assert started.json()["analysis"]["status"] in ("pending", "analyzing", "done")
    await drain_inline_jobs()

    analysis = (await client.get(url, headers=headers)).json()["analysis"]
    assert analysis["status"] == "done"
    assert analysis["stale"] is False
    assert analysis["analyzed_by"] == "mock:mock-1"
    assert [m["skill"] for m in analysis["result"]["missing"]] == ["Terraform"]

    # Asking again reuses the fresh analysis instead of spending quota.
    await client.post(f"{url}/analysis", headers=headers)
    await drain_inline_jobs()
    assert await session.scalar(select(func.count()).select_from(JobMatch)) == 1

    # A changed posting makes it stale.
    market["py"].content_hash = "edited"
    await session.commit()
    assert (await client.get(url, headers=headers)).json()["analysis"]["stale"] is True


async def test_analysis_quota_and_missing_profile(
    client: AsyncClient, login: LoginFn, market: dict[str, Job], use_settings: UseSettings
) -> None:
    nobody = await login("nobody@example.com")
    url = f"/api/v1/jobs/{market['py'].id}/match"
    assert (await client.get(url, headers=nobody)).json()["available"] is False
    refused = await client.post(f"{url}/analysis", headers=nobody)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "no_profile_data"

    headers = await seeker(client, login)
    use_settings(match_analysis_daily_limit=1)
    assert (await client.post(f"{url}/analysis", headers=headers)).status_code == 202
    other = await client.post(f"/api/v1/jobs/{market['fe'].id}/match/analysis", headers=headers)
    assert other.status_code == 429
    assert other.json()["error"]["code"] == "quota_exceeded"


async def test_score_is_partial_until_the_resume_is_re_embedded(
    client: AsyncClient, login: LoginFn, market: dict[str, Job], session: AsyncSession
) -> None:
    headers = await seeker(client, login)
    resume = await session.scalar(select(Resume))
    assert resume is not None
    resume.embedding_model = "mock:mock-1"  # an old vector, from before the text recipe
    await session.commit()

    first = (await client.get(f"/api/v1/jobs/{market['py'].id}/match", headers=headers)).json()
    assert first["embedding_pending"] is True
    assert first["summary"]["partial"] is True
    await drain_inline_jobs()  # the request queued a re-embed
    second = (await client.get(f"/api/v1/jobs/{market['py'].id}/match", headers=headers)).json()
    assert second["embedding_pending"] is False
    assert second["summary"]["partial"] is False


async def test_recommendations(
    client: AsyncClient, login: LoginFn, market: dict[str, Job], session: AsyncSession
) -> None:
    nobody = await login("nobody@example.com")
    empty = (await client.get("/api/v1/matches/recommended", headers=nobody)).json()
    assert empty == {
        "available": False,
        "items": [],
        "next_cursor": None,
        "total": 0,
        "embedding_pending": False,
    }

    headers = await seeker(client, login)
    body = (await client.get("/api/v1/matches/recommended", headers=headers)).json()
    titles = [item["job"]["title"] for item in body["items"]]
    assert titles[0] == "Senior Backend Engineer"
    first = body["items"][0]
    assert first["job"]["match"]["score"] >= body["items"][-1]["job"]["match"]["score"]
    assert any("skills it asks for" in reason for reason in first["reasons"])

    page = (
        await client.get("/api/v1/matches/recommended", params={"limit": 1}, headers=headers)
    ).json()
    assert len(page["items"]) == 1
    assert page["next_cursor"]
    remote = (
        await client.get("/api/v1/matches/recommended", params={"remote": True}, headers=headers)
    ).json()
    assert [i["job"]["title"] for i in remote["items"]] == ["Frontend Engineer"]
    elsewhere = (
        await client.get("/api/v1/matches/recommended", params={"country": "US"}, headers=headers)
    ).json()
    assert elsewhere["items"] == []  # every job here is in India

    # Preferences nudge the ranking and explain themselves.
    user_id = await session.scalar(select(Resume.user_id))
    profile = await session.get(Profile, user_id)
    assert profile is not None
    profile.preferred_locations = ["Bangalore"]
    await session.commit()
    body = (await client.get("/api/v1/matches/recommended", headers=headers)).json()
    reasons: list[str] = body["items"][0]["reasons"]
    assert any("Bengaluru" in r for r in reasons)


async def test_recommendations_list_each_role_once(
    client: AsyncClient,
    login: LoginFn,
    market: dict[str, Job],
    fake: FakePlugin,  # noqa: F811
) -> None:
    from app.modules.jobs.ingestion import ingest_source

    headers = await seeker(client, login)
    # The same opening, posted again for another city (a separate listing in search).
    postings = fake.scopes["fake:a"]
    assert postings is not None
    postings.append(
        posting("py-pune", title="Senior  Backend Engineer", location="Pune, India",
                body="<p>Python, FastAPI, PostgreSQL, Docker, Kubernetes and Terraform.</p>")
    )  # fmt: skip
    await ingest_source("fake")
    await drain_inline_jobs()
    body = (await client.get("/api/v1/matches/recommended", headers=headers)).json()
    titles = [" ".join(i["job"]["title"].split()) for i in body["items"]]
    assert titles.count("Senior Backend Engineer") == 1


async def test_admin_embedding_controls(
    client: AsyncClient, login: LoginFn, market: dict[str, Job], session: AsyncSession
) -> None:
    from app.core.rbac import Role

    support = await login("helper@example.com", Role.SUPPORT)
    assert (
        await client.get("/api/v1/admin/matching/embeddings", headers=support)
    ).status_code == 403

    admin = await login(ROOT_ADMIN_EMAIL)
    status: dict[str, Any] = (
        await client.get("/api/v1/admin/matching/embeddings", headers=admin)
    ).json()
    assert status == {"model": "mock:mock-1#t1", "listed": 4, "embedded": 4, "pending": 0}

    market["fe"].content_hash = "changed"
    await session.commit()
    started = await client.post("/api/v1/admin/matching/embeddings/run", headers=admin)
    assert started.status_code == 202
    await drain_inline_jobs()
    status = (await client.get("/api/v1/admin/matching/embeddings", headers=admin)).json()
    assert status["pending"] == 0
    assert (
        await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "matching.embed_requested")
        )
        == 1
    )
