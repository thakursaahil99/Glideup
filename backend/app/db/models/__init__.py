"""Import every model here so Alembic and `Base.metadata` see the full schema."""

from app.db.models.audit import AuditLog
from app.db.models.llm import LLMUsage
from app.db.models.profile import Profile, RemotePreference
from app.db.models.resume import EMBEDDING_DIMENSIONS, Resume, ResumeSkill, ResumeStatus
from app.db.models.user import RefreshToken, Role, User, UserRole, UserStatus

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "AuditLog",
    "LLMUsage",
    "Profile",
    "RefreshToken",
    "RemotePreference",
    "Resume",
    "ResumeSkill",
    "ResumeStatus",
    "Role",
    "User",
    "UserRole",
    "UserStatus",
]
