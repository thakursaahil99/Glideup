"""Request/response models for profile and resume endpoints."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import RemotePreference, ResumeStatus
from app.modules.resumes.schemas import ParsedResume


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str | None
    email: str
    headline: str | None
    bio: str | None
    years_experience: float | None
    target_roles: list[str]
    preferred_locations: list[str]
    remote_preference: RemotePreference
    onboarding_completed: bool
    has_resume: bool


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    headline: str | None = Field(default=None, max_length=200)
    bio: str | None = Field(default=None, max_length=2000)
    years_experience: float | None = Field(default=None, ge=0, le=60)
    target_roles: list[str] = Field(default_factory=list, max_length=10)
    preferred_locations: list[str] = Field(default_factory=list, max_length=10)
    remote_preference: RemotePreference = RemotePreference.ANY
    complete_onboarding: bool = False


class ResumeSkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    category: str | None
    years: Decimal | None
    level: str | None


class ResumeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    size_bytes: int
    page_count: int | None
    is_active: bool
    status: ResumeStatus
    error: str | None
    parsed_by: str | None
    parsed_at: datetime | None
    created_at: datetime
    has_embedding: bool


class ResumeOut(ResumeSummary):
    parsed: ParsedResume | None
    skills: list[ResumeSkillOut]
    user_edited_at: datetime | None
