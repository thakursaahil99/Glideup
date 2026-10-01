"""Import every model here so Alembic and `Base.metadata` see the full schema."""

from app.db.models.audit import AuditLog
from app.db.models.jobs import (
    ATS,
    Company,
    ExperienceLevel,
    IngestionRun,
    Job,
    JobSource,
    RunStatus,
    SavedJob,
    WorkMode,
)
from app.db.models.llm import LLMUsage
from app.db.models.profile import Profile, RemotePreference
from app.db.models.resume import EMBEDDING_DIMENSIONS, Resume, ResumeSkill, ResumeStatus
from app.db.models.user import RefreshToken, Role, User, UserRole, UserStatus

__all__ = [
    "ATS",
    "EMBEDDING_DIMENSIONS",
    "AuditLog",
    "Company",
    "ExperienceLevel",
    "IngestionRun",
    "Job",
    "JobSource",
    "LLMUsage",
    "Profile",
    "RefreshToken",
    "RemotePreference",
    "Resume",
    "ResumeSkill",
    "ResumeStatus",
    "Role",
    "RunStatus",
    "SavedJob",
    "User",
    "UserRole",
    "UserStatus",
    "WorkMode",
]
