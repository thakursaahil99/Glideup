import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, SessionDep
from app.api.v1.profile_schemas import ResumeOut, ResumeSummary
from app.core.config import get_settings
from app.core.errors import ErrorResponse, NotFoundError
from app.core.ratelimit import rate_limit
from app.core.storage import ObjectNotFoundError, resume_storage
from app.db.models import Resume
from app.modules.resumes import service, tasks
from app.modules.resumes.schemas import ParsedResume
from app.modules.resumes.service import ResumeTooLargeError
from app.workers.runtime import dispatch

router = APIRouter(
    prefix="/resumes",
    tags=["resumes"],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


def _summary_fields(resume: Resume) -> dict[str, object]:
    return {
        "id": resume.id,
        "original_filename": resume.original_filename,
        "size_bytes": resume.size_bytes,
        "page_count": resume.page_count,
        "is_active": resume.is_active,
        "status": resume.status,
        "error": resume.error,
        "parsed_by": resume.parsed_by,
        "parsed_at": resume.parsed_at,
        "created_at": resume.created_at,
        "has_embedding": resume.embedding is not None,
    }


def to_summary(resume: Resume) -> ResumeSummary:
    return ResumeSummary.model_validate(_summary_fields(resume))


def to_out(resume: Resume) -> ResumeOut:
    return ResumeOut.model_validate(
        {
            **_summary_fields(resume),
            "parsed": resume.parsed,
            "skills": resume.skills,
            "user_edited_at": resume.user_edited_at,
        }
    )


@router.post(
    "",
    response_model=ResumeOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={413: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    dependencies=[Depends(rate_limit("upload"))],
)
async def upload_resume(
    session: SessionDep,
    user: CurrentUser,
    file: Annotated[UploadFile, File(description="Resume as a PDF")],
) -> JSONResponse:
    """Upload a PDF resume. Parsing runs in the background; poll GET /resumes/{id}."""
    limit = get_settings().resume_max_bytes
    data = await file.read(limit + 1)  # read at most limit+1: never buffer huge uploads
    if len(data) > limit:
        raise ResumeTooLargeError(f"Resumes can be at most {limit // (1024 * 1024)} MB.")
    resume, created = await service.upload(session, user, filename=file.filename, data=data)
    await session.commit()
    if created:
        dispatch(tasks.parse_resume, service.parse_resume_job, str(resume.id))
    await session.refresh(resume)
    code = status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK
    return JSONResponse(status_code=code, content=to_out(resume).model_dump(mode="json"))


@router.get("", response_model=list[ResumeSummary])
async def list_resumes(session: SessionDep, user: CurrentUser) -> list[ResumeSummary]:
    return [to_summary(r) for r in await service.list_for_user(session, user.id)]


@router.get("/active", response_model=ResumeOut)
async def active_resume(session: SessionDep, user: CurrentUser) -> ResumeOut:
    resume = await service.get_active(session, user.id)
    if resume is None:
        raise NotFoundError("You haven't uploaded a resume yet", code="no_resume")
    return to_out(resume)


@router.get("/{resume_id}", response_model=ResumeOut)
async def get_resume(resume_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> ResumeOut:
    return to_out(await service.get_owned(session, user, resume_id))


@router.get(
    "/{resume_id}/file",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_resume(resume_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> Response:
    resume = await service.get_owned(session, user, resume_id)
    try:
        data = await resume_storage().get(resume.storage_key)
    except ObjectNotFoundError as exc:
        raise NotFoundError("The file for this resume is missing") from exc
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{resume.original_filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.put("/{resume_id}/parsed", response_model=ResumeOut)
async def edit_parsed(
    resume_id: uuid.UUID, body: ParsedResume, session: SessionDep, user: CurrentUser
) -> ResumeOut:
    """Save the user's corrections to the parsed resume, then refresh its embedding."""
    resume = await service.get_owned(session, user, resume_id)
    await service.update_parsed(session, resume, body)
    await session.commit()
    dispatch(tasks.embed_resume, service.embed_resume_job, str(resume.id))
    return to_out(resume)


@router.post("/{resume_id}/reparse", response_model=ResumeOut, status_code=status.HTTP_202_ACCEPTED)
async def reparse(resume_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> ResumeOut:
    resume = await service.get_owned(session, user, resume_id)
    await service.mark_for_reparse(session, resume)
    await session.commit()
    dispatch(tasks.parse_resume, service.parse_resume_job, str(resume.id))
    return to_out(resume)


@router.post("/{resume_id}/activate", response_model=ResumeOut)
async def activate(resume_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> ResumeOut:
    resume = await service.get_owned(session, user, resume_id)
    return to_out(await service.activate(session, resume))


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(resume_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> None:
    resume = await service.get_owned(session, user, resume_id)
    await service.delete(session, resume)
