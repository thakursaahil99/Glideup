"""Request/response models for job search and Jobs & Sources admin."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import ATS, ExperienceLevel, RunStatus, WorkMode


class JobCard(BaseModel):
    id: uuid.UUID
    title: str
    company_name: str
    location: str | None
    country: str | None
    countries: list[str]
    states: list[str]
    cities: list[str]
    remote_scope: Literal["country", "worldwide"] | None
    work_mode: WorkMode
    experience_level: ExperienceLevel
    employment_type: str | None
    skills: list[str]
    posted_at: datetime | None
    first_seen_at: datetime
    salary: str | None
    is_featured: bool
    is_saved: bool
    source: str
    attribution: str | None


class JobDetail(JobCard):
    department: str | None
    description_html: str
    apply_url: str
    is_active: bool
    last_seen_at: datetime


class JobSearchResponse(BaseModel):
    items: list[JobCard]
    next_cursor: str | None
    total: int
    facets: dict[str, dict[str, int]]
    search_backend: str
    took_ms: int


class SavedJobOut(BaseModel):
    saved_at: datetime
    job: JobCard


# --- admin ---


class IngestionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trigger: str
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None
    fetched: int
    created: int
    updated: int
    deactivated: int
    duplicates: int
    errors: list[str]


class JobSourceOut(BaseModel):
    key: str
    name: str
    enabled: bool
    schedule_minutes: int
    rate_limit_per_minute: int
    config: dict[str, Any]
    uses_company_boards: bool
    # Choices for the admin UI (e.g. Adzuna's supported countries); None = no settings.
    config_options: dict[str, Any] | None
    not_configured_reason: str | None
    last_run_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    consecutive_failures: int
    active_jobs: int
    last_run: IngestionRunOut | None


class JobSourceUpdate(BaseModel):
    enabled: bool | None = None
    schedule_minutes: int | None = Field(default=None, ge=15, le=7 * 24 * 60)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=600)
    config: dict[str, Any] | None = None


class RunStarted(BaseModel):
    source: str
    status: Literal["started"] = "started"


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    ats: ATS
    board_token: str
    website: str | None
    enabled: bool
    last_fetched_at: datetime | None
    last_error: str | None
    active_jobs: int


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    ats: ATS
    board_token: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    website: str | None = Field(default=None, max_length=300)


class CompanyUpdate(BaseModel):
    enabled: bool


class CompanyImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]


class AdminJobOut(BaseModel):
    id: uuid.UUID
    title: str
    company_name: str
    location: str | None
    source: str
    is_active: bool
    is_hidden: bool
    is_featured: bool
    duplicate_of_id: uuid.UUID | None
    duplicate_of_title: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    apply_url: str


class JobFlagsUpdate(BaseModel):
    hidden: bool | None = None
    featured: bool | None = None


class ReindexResult(BaseModel):
    indexed: int
