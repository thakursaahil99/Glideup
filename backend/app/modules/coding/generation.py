"""AI question generation with automatic validation.

The model writes a problem, test inputs and a Python reference solution. It does NOT write
expected outputs: the sandbox runs the reference on every input to produce them. So a
question can only reach review if its reference actually runs, within limits, on all of its
tests. An admin then approves (optionally publishing) or rejects it.
"""

import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.db.models import (
    GenerationStatus,
    Language,
    Question,
    QuestionGeneration,
    QuestionStatus,
    QuestionTemplate,
    TestCase,
    User,
)
from app.db.session import session_factory
from app.llm import prompt_store
from app.llm.factory import get_gateway
from app.llm.routing import Task
from app.llm.types import AllProvidersFailedError, CallContext
from app.modules.coding import heuristics  # noqa: F401  (registers the mock)
from app.modules.coding.languages import STARTERS
from app.modules.coding.runner import RunRequest, get_runner
from app.modules.coding.service import ensure_languages

logger = structlog.get_logger(__name__)

REFERENCE_LANGUAGE = "python"


class GeneratedTest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    input: str = Field(max_length=20000)
    hidden: bool = True


class GeneratedQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    title: str = Field(min_length=3, max_length=120)
    statement: str = Field(min_length=20, max_length=6000)
    topics: list[Annotated[str, Field(max_length=40)]] = Field(default_factory=list, max_length=5)
    tests: list[GeneratedTest] = Field(min_length=3, max_length=15)
    reference_solution: str = Field(min_length=10, max_length=10000)

    @field_validator("reference_solution")
    @classmethod
    def _strip_fences(cls, value: str) -> str:
        return re.sub(r"^```\w*\n|\n?```$", "", value.strip())


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80] or "question"


async def request(
    session: AsyncSession, actor: User, topic: str, difficulty: Any
) -> QuestionGeneration:
    from app.modules.platform.service import require_flag

    await require_flag(session, "ai_question_generation", actor.id)
    item = QuestionGeneration(topic=topic, difficulty=difficulty, requested_by_id=actor.id)
    session.add(item)
    await session.commit()
    from app.modules.coding import tasks

    dispatch_generation(tasks, item.id)
    return item


def dispatch_generation(tasks: Any, item_id: uuid.UUID) -> None:
    from app.workers.runtime import dispatch

    dispatch(tasks.generate_question, generate_job, str(item_id))


async def generate_job(item_id: str) -> None:
    """Never leaves an item stuck in `generating`: unexpected errors mark it failed."""
    try:
        await _generate(item_id)
    except Exception as exc:
        logger.exception("question_generation_crashed", item_id=item_id)
        async with session_factory()() as session:
            item = await session.get(QuestionGeneration, uuid.UUID(item_id))
            if item is not None and item.status == GenerationStatus.GENERATING:
                item.status = GenerationStatus.FAILED
                item.error = f"Generation failed unexpectedly: {type(exc).__name__}"
                await session.commit()


async def _generate(item_id: str) -> None:
    async with session_factory()() as session:
        item = await session.get(QuestionGeneration, uuid.UUID(item_id))
        if item is None or item.status not in (GenerationStatus.PENDING, GenerationStatus.FAILED):
            return
        item.status = GenerationStatus.GENERATING
        item.error = None
        await session.commit()

        messages, version = await prompt_store.render(
            "question_generate", topic=item.topic, difficulty=item.difficulty.value
        )
        try:
            generated, result = await get_gateway().complete_json(
                Task.QUESTION_GENERATE,
                messages,
                GeneratedQuestion,
                ctx=CallContext(prompt_version=version),
                max_tokens=4000,
            )
        except AllProvidersFailedError as exc:
            item.status = GenerationStatus.FAILED
            item.error = f"No model could write the question: {exc}"[:2000]
            await session.commit()
            return
        item.generated_by = f"{result.provider}:{result.model}"

        await ensure_languages(session)
        language = await session.get(Language, REFERENCE_LANGUAGE)
        if language is None:  # ensure_languages just created it; only an admin delete could
            item.status = GenerationStatus.FAILED
            item.error = "Python isn't configured as a language."
            await session.commit()
            return
        await session.commit()
        tests: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        runner = get_runner()
        for position, test in enumerate(generated.tests):
            run = await runner.run(
                RunRequest(
                    REFERENCE_LANGUAGE,
                    generated.reference_solution,
                    test.input,
                    language.time_limit_s,
                    language.memory_limit_mb,
                )
            )
            if run.status != "ok" or not run.stdout.strip():
                failures.append(
                    {
                        "position": position,
                        "status": run.status,
                        "stderr": (run.stderr or run.compile_output)[:500],
                    }
                )
            tests.append(
                {
                    "position": position,
                    "input": test.input,
                    "expected_output": run.stdout,
                    "hidden": test.hidden,
                }
            )
        if not any(not t["hidden"] for t in tests) and tests:
            tests[0]["hidden"] = False  # always show at least one example
        if sum(t["hidden"] for t in tests) < 2:
            failures.append({"problem": "needs at least two hidden tests"})

        item.validation = {
            "ok": not failures,
            "at": datetime.now(UTC).isoformat(),
            "failures": failures,
        }
        item.draft = {
            "title": generated.title,
            "slug": slugify(generated.title),
            "statement": generated.statement,
            "topics": generated.topics or [item.topic],
            "tests": tests,
            "reference": {REFERENCE_LANGUAGE: generated.reference_solution},
        }
        if failures:
            item.status = GenerationStatus.FAILED
            item.error = "The reference solution didn't run cleanly on every test."
        else:
            item.status = GenerationStatus.READY
        await session.commit()
        logger.info("question_generated", item_id=item_id, status=item.status.value)


async def approve(
    session: AsyncSession, item: QuestionGeneration, actor: User, *, publish: bool
) -> Question:
    if item.status != GenerationStatus.READY or not item.draft:
        raise ConflictError("Only validated, ready questions can be approved.", code="not_ready")
    draft = item.draft
    slug = draft["slug"]
    from sqlalchemy import select

    taken = set(await session.scalars(select(Question.slug).where(Question.slug.like(f"{slug}%"))))
    suffix = 2
    while slug in taken:
        slug = f"{draft['slug']}-{suffix}"
        suffix += 1
    question = Question(
        slug=slug,
        title=draft["title"],
        difficulty=item.difficulty,
        topics=draft["topics"],
        statement=draft["statement"],
        status=QuestionStatus.PUBLISHED if publish else QuestionStatus.DRAFT,
        source="ai",
        validation=item.validation,
        created_by_id=actor.id,
    )
    question.templates = [
        QuestionTemplate(
            language_key=key,
            starter_code=STARTERS[key],
            reference_solution=draft["reference"].get(key),
        )
        for key in STARTERS
    ]
    question.tests = [TestCase(**t) for t in draft["tests"]]
    session.add(question)
    await session.flush()
    item.status = GenerationStatus.APPROVED
    item.question_id = question.id
    item.reviewed_by_id = actor.id
    item.reviewed_at = datetime.now(UTC)
    return question


def reject(item: QuestionGeneration, actor: User, note: str | None) -> None:
    if item.status not in (GenerationStatus.READY, GenerationStatus.FAILED):
        raise ConflictError("This item can't be rejected now.", code="not_reviewable")
    item.status = GenerationStatus.REJECTED
    item.review_note = note
    item.reviewed_by_id = actor.id
    item.reviewed_at = datetime.now(UTC)
