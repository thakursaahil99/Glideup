"""Request/response models shared by the v1 routers."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.api.v1.profile_schemas import ProfileOut, ResumeOut, ResumeSummary
from app.core.rbac import Role
from app.db.models import UserStatus


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


# --- Auth ---


class GoogleSignInRequest(BaseModel):
    id_token: str = Field(min_length=20, max_length=8192)


class DevSignInRequest(BaseModel):
    email: EmailStr
    name: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=4096)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105  (OAuth token type, not a secret)
    access_expires_at: datetime
    refresh_expires_at: datetime
    user: "MeResponse"


# --- Users ---


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str | None
    avatar_url: str | None
    status: UserStatus
    roles: list[str] = Field(validation_alias="role_names")
    last_login_at: datetime | None
    created_at: datetime


class MeResponse(UserSummary):
    permissions: list[str]


# --- Admin ---


class SetRoleRequest(BaseModel):
    role: Role


class SetStatusRequest(BaseModel):
    status: UserStatus
    reason: str | None = Field(default=None, max_length=500)


class DailyCount(BaseModel):
    date: str
    count: int


class AdminOverview(BaseModel):
    total_users: int
    active_users_30d: int
    new_users_in_range: int
    suspended_users: int
    admin_users: int
    signups_by_day: list[DailyCount]
    range_start: datetime
    range_end: datetime
    resumes_uploaded: int
    resumes_parsed: int
    resumes_failed: int
    llm_calls: int
    llm_failed_calls: int
    llm_tokens: int
    llm_estimated_cost_usd: float


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_email: str | None
    action: str
    target_type: str | None
    target_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip_address: str | None
    request_id: str | None
    created_at: datetime


class RoleOut(BaseModel):
    name: str
    description: str
    permissions: list[str]


class AdminUserDetail(BaseModel):
    user: UserSummary
    suspended_reason: str | None
    profile: ProfileOut | None
    resumes: list[ResumeSummary]
    active_resume: ResumeOut | None
    llm_calls: int
