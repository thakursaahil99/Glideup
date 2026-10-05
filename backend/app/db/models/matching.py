import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MatchAnalysisStatus(enum.StrEnum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    DONE = "done"
    FAILED = "failed"


class JobMatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user's AI skill-gap analysis for one job.

    The match *score* is cheap and computed on every request; only the LLM analysis is
    stored. It is tied to what it was computed from (resume, the job's content hash, the
    user's skill set and the prompt version), so any change makes it stale and the user
    can refresh it.
    """

    __tablename__ = "job_matches"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    resume_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("resumes.id", ondelete="SET NULL")
    )
    status: Mapped[MatchAnalysisStatus] = mapped_column(
        Enum(
            MatchAnalysisStatus,
            name="match_analysis_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=MatchAnalysisStatus.PENDING,
        server_default=MatchAnalysisStatus.PENDING.value,
        nullable=False,
    )
    score: Mapped[int | None] = mapped_column(Integer)  # the score when analysed (0-100)
    # Validated `SkillGapAnalysis` JSON.
    analysis: Mapped[dict[str, Any] | None]
    error: Mapped[str | None] = mapped_column(Text)
    job_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    skills_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    analyzed_by: Mapped[str | None] = mapped_column(String(200))  # "provider:model"
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("uq_job_matches_user_job", "user_id", "job_id", unique=True),
        Index("ix_job_matches_user_requested", "user_id", "requested_at"),
    )
