import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    false,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class Difficulty(enum.StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class InterviewStatus(enum.StrEnum):
    PREPARING = "preparing"  # writing the questions (job-specific interviews)
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"  # couldn't be prepared


class ReportStatus(enum.StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"  # nothing was answered


class InterviewType(TimestampMixin, Base):
    """A kind of interview and its settings, editable in the admin console."""

    __tablename__ = "interview_types"

    key: Mapped[str] = mapped_column(String(30), primary_key=True)  # dsa, behavioral, ...
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    max_followups: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[Difficulty] = mapped_column(_enum(Difficulty, "difficulty"), nullable=False)
    # [{"key", "name", "description", "weight"}]; the report scores each criterion 1-5.
    rubric: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Interview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "interviews"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type_key: Mapped[str] = mapped_column(
        String(30), ForeignKey("interview_types.key", ondelete="RESTRICT"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="SET NULL")
    )
    resume_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("resumes.id", ondelete="SET NULL")
    )
    status: Mapped[InterviewStatus] = mapped_column(
        _enum(InterviewStatus, "interview_status"), nullable=False
    )
    # Settings are copied at creation, so later admin edits don't change a running interview
    # (or how a finished one is read).
    difficulty: Mapped[Difficulty] = mapped_column(_enum(Difficulty, "difficulty"), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    max_followups: Mapped[int] = mapped_column(Integer, nullable=False)
    rubric: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    # [{"prompt", "focus", "kind", "expected_points": [...]}]
    plan: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    job_title: Mapped[str | None] = mapped_column(String(300))
    company_name: Mapped[str | None] = mapped_column(String(200))

    current_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    followups_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    hints_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[str | None] = mapped_column(String(20))  # finished|time_up|ended_early
    error: Mapped[str | None] = mapped_column(Text)
    # Single-use WebSocket ticket currently allowed to connect.
    ws_ticket_jti: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    __table_args__ = (
        Index("ix_interviews_user_created", "user_id", "created_at"),
        Index("ix_interviews_status_ends", "status", "ends_at"),
    )


class InterviewMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "interview_messages"

    interview_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(15), nullable=False)  # interviewer | candidate
    # intro | question | followup | hint | answer | closing
    kind: Mapped[str] = mapped_column(String(15), nullable=False)
    question_index: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    attachment: Mapped[str | None] = mapped_column(Text)  # code or design notes
    client_id: Mapped[str | None] = mapped_column(String(64))  # idempotency for answers
    interrupted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("uq_interview_messages_seq", "interview_id", "seq", unique=True),
        Index(
            "uq_interview_messages_client",
            "interview_id",
            "client_id",
            unique=True,
            postgresql_where=text("client_id IS NOT NULL"),
            sqlite_where=text("client_id IS NOT NULL"),
        ),
    )


class InterviewReport(TimestampMixin, Base):
    __tablename__ = "interview_reports"

    interview_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("interviews.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[ReportStatus] = mapped_column(
        _enum(ReportStatus, "report_status"), nullable=False
    )
    overall_score: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[dict[str, Any] | None]  # validated InterviewReportResult
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    generated_by: Mapped[str | None] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
