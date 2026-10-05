"""Coding practice for users: browse problems, run examples, submit for grading."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Query, status

from app.api.deps import CurrentUser, SessionDep
from app.api.v1.coding_schemas import (
    CaseResultOut,
    CodeIn,
    ExampleOut,
    LanguageOut,
    ProblemDetail,
    ProblemSummary,
    RunResultOut,
    SubmissionDetail,
    SubmissionOut,
)
from app.core.errors import ErrorResponse
from app.db.models import Difficulty
from app.modules.coding import service

router = APIRouter(
    tags=["problems"],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


@router.get("/problems/languages", response_model=list[LanguageOut])
async def languages(session: SessionDep, _: CurrentUser) -> list[LanguageOut]:
    items = await service.list_languages(session)
    await session.commit()
    return [LanguageOut.model_validate(lang) for lang in items]


@router.get("/problems", response_model=list[ProblemSummary])
async def list_problems(
    session: SessionDep,
    user: CurrentUser,
    difficulty: Difficulty | None = None,
    topic: Annotated[str | None, Query(max_length=40)] = None,
) -> list[ProblemSummary]:
    rows = await service.list_problems(session, user, difficulty=difficulty, topic=topic)
    return [
        ProblemSummary(
            slug=r.question.slug,
            title=r.question.title,
            difficulty=r.question.difficulty,
            topics=r.question.topics,
            solved=r.solved,
            attempted=r.attempted,
        )
        for r in rows
    ]


@router.get("/problems/{slug}", response_model=ProblemDetail)
async def get_problem(slug: str, session: SessionDep, _: CurrentUser) -> ProblemDetail:
    question = await service.get_problem(session, slug)
    langs = await service.list_languages(session)
    await session.commit()
    return ProblemDetail(
        slug=question.slug,
        title=question.title,
        difficulty=question.difficulty,
        topics=question.topics,
        statement=question.statement,
        examples=[
            ExampleOut(input=t.input, expected_output=t.expected_output)
            for t in question.tests
            if not t.hidden
        ],
        hidden_tests=sum(t.hidden for t in question.tests),
        starters={lang.key: service.starter_for(question, lang.key) for lang in langs},
        languages=[LanguageOut.model_validate(lang) for lang in langs],
    )


@router.post(
    "/problems/{slug}/run",
    response_model=RunResultOut,
    responses={400: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
)
async def run_examples(
    slug: str, body: CodeIn, session: SessionDep, user: CurrentUser
) -> RunResultOut:
    """Run against the visible examples only. Nothing is stored."""
    question = await service.get_problem(session, slug)
    result = await service.run_examples(session, user, question, body.language, body.code)
    return RunResultOut(
        verdict=result.verdict,
        passed=result.passed,
        total=result.total,
        results=[CaseResultOut.model_validate(r) for r in result.results],
        compile_output=result.compile_output,
        max_time_ms=result.max_time_ms,
    )


@router.post(
    "/problems/{slug}/submissions",
    response_model=SubmissionOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={400: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
)
async def submit(
    slug: str,
    body: CodeIn,
    session: SessionDep,
    user: CurrentUser,
    idempotency_key: Annotated[
        str | None,
        Header(max_length=100, description="Repeat-safe: the same key returns the same submission"),
    ] = None,
) -> SubmissionOut:
    """Grade against every test, including hidden ones (in the background; poll the
    submission until its verdict is final)."""
    question = await service.get_problem(session, slug)
    submission = await service.submit(
        session, user, question, body.language, body.code, idempotency_key
    )
    return SubmissionOut.model_validate(submission)


@router.get("/problems/{slug}/submissions", response_model=list[SubmissionOut])
async def my_submissions(slug: str, session: SessionDep, user: CurrentUser) -> list[SubmissionOut]:
    question = await service.get_problem(session, slug)
    return [
        SubmissionOut.model_validate(s)
        for s in await service.my_submissions(session, user, question)
    ]


@router.get("/submissions/{submission_id}", response_model=SubmissionDetail)
async def get_submission(
    submission_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> SubmissionDetail:
    return SubmissionDetail.model_validate(
        await service.get_submission(session, user, submission_id)
    )
