"""Admin: languages, the question bank (with sandbox validation) and the AI generation queue."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import or_, select

from app.api.deps import RequestMetaDep, SessionDep, require_permission
from app.api.v1.coding_schemas import (
    GenerationOut,
    GenerationRequest,
    GenerationReview,
    LanguageAdmin,
    LanguageUpdate,
    QuestionAdminDetail,
    QuestionAdminSummary,
    QuestionIn,
    QuestionStatusUpdate,
    TemplateIn,
    TestCaseIn,
)
from app.core.errors import AppError, ConflictError, ErrorResponse, NotFoundError
from app.core.rbac import Permission
from app.db.models import (
    Framework,
    GenerationStatus,
    Language,
    Question,
    QuestionGeneration,
    QuestionStatus,
    QuestionTemplate,
    TestCase,
    User,
)
from app.modules.audit import service as audit
from app.modules.coding import generation, service, tasks
from app.modules.skills.content import validate_content

router = APIRouter(
    prefix="/admin",
    tags=["admin: question bank"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)

QuestionsAdmin = Annotated[User, Depends(require_permission(Permission.QUESTIONS_MANAGE))]


# ------------------------------------------------------------------ languages


@router.get("/languages", response_model=list[LanguageAdmin])
async def list_languages(session: SessionDep, _: QuestionsAdmin) -> list[LanguageAdmin]:
    items = await service.list_languages(session, enabled_only=False)
    await session.commit()
    return [LanguageAdmin.model_validate(i) for i in items]


@router.patch("/languages/{key}", response_model=LanguageAdmin)
async def update_language(
    key: str, body: LanguageUpdate, session: SessionDep, actor: QuestionsAdmin, meta: RequestMetaDep
) -> LanguageAdmin:
    language = await session.get(Language, key)
    if language is None:
        raise NotFoundError("Language not found")
    changes = body.model_dump(exclude_unset=True)
    before = {k: getattr(language, k) for k in changes}
    for field, value in changes.items():
        setattr(language, field, value)
    await audit.record(
        session,
        actor=actor,
        action="language.updated",
        target_type="language",
        target_id=key,
        before=before,
        after=changes,
        meta=meta,
    )
    await session.commit()
    return LanguageAdmin.model_validate(language)


# ------------------------------------------------------------------ questions


def _detail(question: Question, stats: dict[uuid.UUID, dict[str, Any]]) -> QuestionAdminDetail:
    return QuestionAdminDetail(
        id=question.id,
        type=question.type,
        framework_key=question.framework_key,
        content=question.content,
        slug=question.slug,
        title=question.title,
        difficulty=question.difficulty,
        topics=question.topics,
        statement=question.statement,
        status=question.status,
        source=question.source,
        validation=question.validation,
        templates=[
            TemplateIn(
                language_key=t.language_key,
                starter_code=t.starter_code,
                reference_solution=t.reference_solution,
            )
            for t in question.templates
        ],
        tests=[
            TestCaseIn(input=t.input, expected_output=t.expected_output, hidden=t.hidden)
            for t in question.tests
        ],
        stats=stats.get(question.id),
    )


async def _get(session: SessionDep, question_id: uuid.UUID) -> Question:
    question = await session.get(Question, question_id)
    if question is None:
        raise NotFoundError("Question not found")
    return question


async def _apply(session: SessionDep, question: Question, body: QuestionIn) -> None:
    if body.type == "dsa":
        if not body.tests:
            raise AppError("Coding problems need at least one test.", code="tests_required")
        question.content = None
        question.framework_key = None
    else:
        if not body.framework_key or await session.get(Framework, body.framework_key) is None:
            raise AppError(
                "Pick the framework this question belongs to.", code="framework_required"
            )
        try:
            question.content = validate_content(body.type, body.content or {})
        except ValueError as exc:
            raise AppError(f"Invalid {body.type} content: {exc}", code="invalid_content") from exc
        question.framework_key = body.framework_key
    question.type = body.type
    keys = {lang.key for lang in await service.list_languages(session, enabled_only=False)}
    unknown = {t.language_key for t in body.templates} - keys
    if unknown:
        raise AppError(
            f"Unknown language(s): {', '.join(sorted(unknown))}", code="invalid_language"
        )
    clash = await session.scalar(
        select(Question.id).where(Question.slug == body.slug, Question.id != question.id)
    )
    if clash:
        raise ConflictError("Another question already uses this slug.", code="slug_taken")
    question.slug, question.title, question.difficulty = body.slug, body.title, body.difficulty
    question.topics, question.statement = body.topics, body.statement
    # Update templates in place (one per language is unique; replacing the list would insert
    # the new rows before deleting the old ones).
    existing = {t.language_key: t for t in question.templates}
    kept: list[QuestionTemplate] = []
    for t in body.templates:
        row = existing.get(t.language_key) or QuestionTemplate(language_key=t.language_key)
        row.starter_code = t.starter_code
        row.reference_solution = t.reference_solution or None
        kept.append(row)
    question.templates = kept
    question.tests = [
        TestCase(position=i, input=t.input, expected_output=t.expected_output, hidden=t.hidden)
        for i, t in enumerate(body.tests)
    ]
    question.validation = None  # any edit needs a fresh validation run


@router.get("/questions", response_model=list[QuestionAdminSummary])
async def list_questions(
    session: SessionDep,
    _: QuestionsAdmin,
    status_filter: Annotated[QuestionStatus | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> list[QuestionAdminSummary]:
    await service.seed_problems(session)
    await session.commit()
    stmt = select(Question).order_by(Question.updated_at.desc())
    if status_filter:
        stmt = stmt.where(Question.status == status_filter)
    if search:
        term = f"%{search.lower()}%"
        stmt = stmt.where(or_(Question.title.ilike(term), Question.slug.ilike(term)))
    questions = list(await session.scalars(stmt))
    stats = await service.question_stats(session, [q.id for q in questions])
    return [
        QuestionAdminSummary(
            id=q.id,
            type=q.type,
            framework_key=q.framework_key,
            slug=q.slug,
            title=q.title,
            difficulty=q.difficulty,
            topics=q.topics,
            status=q.status,
            source=q.source,
            validated=bool((q.validation or {}).get("ok")),
            tests=len(q.tests),
            updated_at=q.updated_at,
            stats=stats.get(q.id),
        )
        for q in questions
    ]


@router.post(
    "/questions",
    response_model=QuestionAdminDetail,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def create_question(
    body: QuestionIn, session: SessionDep, actor: QuestionsAdmin, meta: RequestMetaDep
) -> QuestionAdminDetail:
    question = Question(
        slug=body.slug,
        title=body.title,
        difficulty=body.difficulty,
        statement=body.statement,
        created_by_id=actor.id,
        source="manual",
    )
    await _apply(session, question, body)
    session.add(question)
    await session.flush()
    await audit.record(
        session,
        actor=actor,
        action="question.created",
        target_type="question",
        target_id=question.id,
        after={"slug": question.slug},
        meta=meta,
    )
    await session.commit()
    return _detail(question, {})


@router.get("/questions/{question_id}", response_model=QuestionAdminDetail)
async def get_question(
    question_id: uuid.UUID, session: SessionDep, _: QuestionsAdmin
) -> QuestionAdminDetail:
    question = await _get(session, question_id)
    return _detail(question, await service.question_stats(session, [question.id]))


@router.put(
    "/questions/{question_id}",
    response_model=QuestionAdminDetail,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def update_question(
    question_id: uuid.UUID,
    body: QuestionIn,
    session: SessionDep,
    actor: QuestionsAdmin,
    meta: RequestMetaDep,
) -> QuestionAdminDetail:
    """Replaces the question. A published question goes back to draft until it is
    validated and published again, so users never see an unvalidated version."""
    question = await _get(session, question_id)
    before = {"status": question.status.value, "tests": len(question.tests)}
    await _apply(session, question, body)
    if question.status == QuestionStatus.PUBLISHED:
        question.status = QuestionStatus.DRAFT
    await audit.record(
        session,
        actor=actor,
        action="question.updated",
        target_type="question",
        target_id=question.id,
        before=before,
        after={"status": question.status.value, "tests": len(body.tests)},
        meta=meta,
    )
    await session.commit()
    return _detail(question, await service.question_stats(session, [question.id]))


@router.post("/questions/{question_id}/validate", response_model=QuestionAdminDetail)
async def validate_question(
    question_id: uuid.UUID, session: SessionDep, _: QuestionsAdmin
) -> QuestionAdminDetail:
    """Run every reference solution against every test in the sandbox."""
    question = await _get(session, question_id)
    await service.validate_question(session, question)
    await session.commit()
    return _detail(question, await service.question_stats(session, [question.id]))


@router.patch(
    "/questions/{question_id}/status",
    response_model=QuestionAdminDetail,
    responses={409: {"model": ErrorResponse}},
)
async def set_status(
    question_id: uuid.UUID,
    body: QuestionStatusUpdate,
    session: SessionDep,
    actor: QuestionsAdmin,
    meta: RequestMetaDep,
) -> QuestionAdminDetail:
    question = await _get(session, question_id)
    if body.status == QuestionStatus.PUBLISHED:
        service.publishable(question)
    before = question.status.value
    question.status = body.status
    await audit.record(
        session,
        actor=actor,
        action="question.status_changed",
        target_type="question",
        target_id=question.id,
        before={"status": before},
        after={"status": body.status.value},
        meta=meta,
    )
    await session.commit()
    return _detail(question, await service.question_stats(session, [question.id]))


# ------------------------------------------------------------------ AI generation queue


@router.post(
    "/question-generation", response_model=list[GenerationOut], status_code=status.HTTP_202_ACCEPTED
)
async def request_generation(
    body: GenerationRequest, session: SessionDep, actor: QuestionsAdmin, meta: RequestMetaDep
) -> list[GenerationOut]:
    items = [
        await generation.request(session, actor, body.topic, body.difficulty)
        for _ in range(body.count)
    ]
    await audit.record(
        session,
        actor=actor,
        action="question.generation_requested",
        target_type="question",
        after={"topic": body.topic, "difficulty": body.difficulty.value, "count": body.count},
        meta=meta,
    )
    await session.commit()
    for item in items:
        await session.refresh(item)
    return [GenerationOut.model_validate(i) for i in items]


@router.get("/question-generation", response_model=list[GenerationOut])
async def list_generation(
    session: SessionDep,
    _: QuestionsAdmin,
    status_filter: Annotated[GenerationStatus | None, Query(alias="status")] = None,
) -> list[GenerationOut]:
    stmt = select(QuestionGeneration).order_by(QuestionGeneration.created_at.desc()).limit(100)
    if status_filter:
        stmt = stmt.where(QuestionGeneration.status == status_filter)
    return [GenerationOut.model_validate(i) for i in await session.scalars(stmt)]


async def _item(session: SessionDep, item_id: uuid.UUID) -> QuestionGeneration:
    item = await session.get(QuestionGeneration, item_id)
    if item is None:
        raise NotFoundError("Generation item not found")
    return item


@router.post(
    "/question-generation/{item_id}/review",
    response_model=GenerationOut,
    responses={409: {"model": ErrorResponse}},
)
async def review_generation(
    item_id: uuid.UUID,
    body: GenerationReview,
    session: SessionDep,
    actor: QuestionsAdmin,
    meta: RequestMetaDep,
) -> GenerationOut:
    item = await _item(session, item_id)
    if body.approve:
        question = await generation.approve(session, item, actor, publish=body.publish)
        action, after = (
            "question.generation_approved",
            {"question": question.slug, "published": body.publish},
        )
    else:
        generation.reject(item, actor, body.note)
        action, after = "question.generation_rejected", {"note": body.note}
    await audit.record(
        session,
        actor=actor,
        action=action,
        target_type="question_generation",
        target_id=item.id,
        after=after,
        meta=meta,
    )
    await session.commit()
    await session.refresh(item)
    return GenerationOut.model_validate(item)


@router.post(
    "/question-generation/{item_id}/retry",
    response_model=GenerationOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {"model": ErrorResponse}},
)
async def retry_generation(
    item_id: uuid.UUID, session: SessionDep, _: QuestionsAdmin
) -> GenerationOut:
    item = await _item(session, item_id)
    if item.status != GenerationStatus.FAILED:
        raise ConflictError("Only failed items can be retried.", code="not_failed")
    item.status = GenerationStatus.PENDING
    await session.commit()
    generation.dispatch_generation(tasks, item.id)
    return GenerationOut.model_validate(item)
