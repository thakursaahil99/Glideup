"""Request/response models for profile and resume endpoints."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.db.models import RemotePreference, ResumeStatus
from app.modules.profiles.links import is_github, is_linkedin, normalize_url
from app.modules.resumes.schemas import ParsedResume


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str | None
    email: str
    headline: str | None
    bio: str | None
    years_experience: float | None
    portfolio_url: str | None
    linkedin_url: str | None
    github_url: str | None
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
    portfolio_url: str | None = Field(default=None, max_length=300)
    linkedin_url: str | None = Field(default=None, max_length=300)
    github_url: str | None = Field(default=None, max_length=300)
    target_roles: list[str] = Field(default_factory=list, max_length=10)
    preferred_locations: list[str] = Field(default_factory=list, max_length=10)
    remote_preference: RemotePreference = RemotePreference.ANY
    complete_onboarding: bool = False

    @field_validator("portfolio_url", "linkedin_url", "github_url")
    @classmethod
    def _normalize_link(cls, value: str | None, info: ValidationInfo) -> str | None:
        url = normalize_url(value)
        if url and info.field_name == "linkedin_url" and not is_linkedin(url):
            raise ValueError("Enter a linkedin.com address")
        if url and info.field_name == "github_url" and not is_github(url):
            raise ValueError("Enter a github.com address")
        return url


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
