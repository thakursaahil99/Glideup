"""Admin: prompt templates with versioning, rollback and a test playground."""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, status
from jinja2 import TemplateError
from sqlalchemy import func, select

from app.api.deps import RequestMetaDep, SessionDep, require_permission
from app.api.v1.interview_schemas import (
    PromptActivate,
    PromptDetail,
    PromptSummary,
    PromptTest,
    PromptTestResult,
    PromptVersionCreate,
    PromptVersionOut,
)
from app.core.errors import AppError, ErrorResponse, NotFoundError
from app.core.rbac import Permission
from app.db.models import PromptTemplate, PromptTemplateVersion, User
from app.llm import prompt_store
from app.llm.factory import get_gateway
from app.llm.prompt_samples import SAMPLES
from app.llm.types import AllProvidersFailedError, CallContext
from app.modules.audit import service as audit

router = APIRouter(
    prefix="/admin/prompts",
    tags=["admin: prompts"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)

PromptsAdmin = Annotated[User, Depends(require_permission(Permission.PROMPTS_MANAGE))]
FREE_TEXT_TASKS = {"interviewer", "interview_hint"}  # everything else answers in JSON


async def _template(session: SessionDep, name: str) -> PromptTemplate:
    await prompt_store.ensure_imported(session)
    template = await session.get(PromptTemplate, name)
    if template is None:
        raise NotFoundError("Prompt template not found")
    return template


async def _versions(
    session: SessionDep, name: str
) -> list[tuple[PromptTemplateVersion, str | None]]:
    rows = await session.execute(
        select(PromptTemplateVersion, User.email)
        .outerjoin(User, User.id == PromptTemplateVersion.created_by_id)
        .where(PromptTemplateVersion.template_name == name)
        .order_by(PromptTemplateVersion.version.desc())
    )
    return [(v, email) for v, email in rows]


async def _detail(session: SessionDep, template: PromptTemplate) -> PromptDetail:
    return PromptDetail(
        name=template.name,
        description=template.description,
        active_version=template.active_version,
        variables=sorted(prompt_store.allowed_variables(template.name) - {"fence"}),
        sample=SAMPLES.get(template.name, {}),
        versions=[
            PromptVersionOut(
                version=v.version,
                system=v.system,
                user=v.user,
                notes=v.notes,
                source=v.source,
                created_by_email=email,
                created_at=v.created_at,
                active=v.version == template.active_version,
            )
            for v, email in await _versions(session, template.name)
        ],
    )


@router.get("", response_model=list[PromptSummary])
async def list_prompts(session: SessionDep, _: PromptsAdmin) -> list[PromptSummary]:
    await prompt_store.ensure_imported(session)
    await session.commit()
    rows = await session.execute(
        select(PromptTemplateVersion.template_name, func.count()).group_by(
            PromptTemplateVersion.template_name
        )
    )
    counts: dict[str, int] = {name: count for name, count in rows}  # noqa: C416
    templates = await session.scalars(select(PromptTemplate).order_by(PromptTemplate.name))
    return [
        PromptSummary(
            name=t.name,
            description=t.description,
            active_version=t.active_version,
            versions=counts.get(t.name, 0),
            updated_at=t.updated_at,
        )
        for t in templates
    ]


@router.get("/{name}", response_model=PromptDetail)
async def get_prompt(name: str, session: SessionDep, _: PromptsAdmin) -> PromptDetail:
    template = await _template(session, name)
    await session.commit()
    return await _detail(session, template)


@router.post(
    "/{name}/versions",
    response_model=PromptDetail,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}},
)
async def create_version(
    name: str,
    body: PromptVersionCreate,
    session: SessionDep,
    actor: PromptsAdmin,
    meta: RequestMetaDep,
) -> PromptDetail:
    """Save an edited prompt as a new version (validated first); optionally make it live."""
    template = await _template(session, name)
    problems = prompt_store.validate(name, body.system, body.user)
    if problems:
        raise AppError("The template has problems.", code="invalid_template", details=problems)
    latest = await session.scalar(
        select(func.max(PromptTemplateVersion.version)).where(
            PromptTemplateVersion.template_name == name
        )
    )
    version = PromptTemplateVersion(
        template_name=name,
        version=(latest or 0) + 1,
        system=body.system,
        user=body.user,
        notes=body.notes,
        source="admin",
        created_by_id=actor.id,
    )
    session.add(version)
    before = {"active_version": template.active_version}
    if body.activate:
        template.active_version = version.version
    await audit.record(
        session,
        actor=actor,
        action="prompt.version_created",
        target_type="prompt_template",
        target_id=name,
        before=before,
        after={"version": version.version, "active_version": template.active_version},
        meta=meta,
    )
    await session.commit()
    prompt_store.invalidate(name)
    return await _detail(session, template)


@router.post(
    "/{name}/activate", response_model=PromptDetail, responses={400: {"model": ErrorResponse}}
)
async def activate_version(
    name: str,
    body: PromptActivate,
    session: SessionDep,
    actor: PromptsAdmin,
    meta: RequestMetaDep,
) -> PromptDetail:
    """Make a version live: publish a new one, or roll back to an older one."""
    template = await _template(session, name)
    exists = await session.scalar(
        select(PromptTemplateVersion.id).where(
            PromptTemplateVersion.template_name == name,
            PromptTemplateVersion.version == body.version,
        )
    )
    if exists is None:
        raise NotFoundError(f"Version {body.version} not found")
    if template.active_version != body.version:
        await audit.record(
            session,
            actor=actor,
            action="prompt.activated",
            target_type="prompt_template",
            target_id=name,
            before={"active_version": template.active_version},
            after={"active_version": body.version},
            meta=meta,
        )
        template.active_version = body.version
        await session.commit()
        prompt_store.invalidate(name)
    return await _detail(session, template)


@router.post(
    "/{name}/test",
    response_model=PromptTestResult,
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def test_prompt(
    name: str, body: PromptTest, session: SessionDep, actor: PromptsAdmin
) -> PromptTestResult:
    """Render a saved version (or unsaved text) with example variables and run it once
    through the same model route production uses. Nothing is saved."""
    template = await _template(session, name)
    if body.system is not None:
        system, user = body.system, body.user or ""
        problems = prompt_store.validate(name, system, user)
        if problems:
            raise AppError("The template has problems.", code="invalid_template", details=problems)
    else:
        number = body.version or template.active_version
        version = await session.scalar(
            select(PromptTemplateVersion).where(
                PromptTemplateVersion.template_name == name,
                PromptTemplateVersion.version == number,
            )
        )
        if version is None:
            raise NotFoundError("Version not found")
        system, user = version.system, version.user
    await session.commit()
    variables = {**SAMPLES.get(name, {}), **body.variables}
    try:
        messages = prompt_store.render_text(system, user, **variables)
    except TemplateError as exc:
        raise AppError(f"Rendering failed: {exc}", code="render_failed") from exc
    started = time.perf_counter()
    try:
        result = await get_gateway().complete(
            name,
            messages,
            json_output=name not in FREE_TEXT_TASKS,
            ctx=CallContext(user_id=actor.id, prompt_version=f"{name}@playground"),
        )
    except AllProvidersFailedError as exc:
        error = AppError(f"No model answered: {exc}", code="llm_unavailable")
        error.status_code = 503
        raise error from exc
    return PromptTestResult(
        messages=[{"role": m.role, "content": m.content} for m in messages],
        output=result.text,
        provider=result.provider,
        model=result.model,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
