"""Application tracker, reminders, and user-submitted reports (feedback queue)."""

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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class ApplicationStatus(enum.StrEnum):
    SAVED = "saved"  # interested, not applied yet
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ReportKind(enum.StrEnum):
    WRONG_QUESTION = "wrong_question"
    BAD_AI_FEEDBACK = "bad_ai_feedback"
    BROKEN_JOB_LINK = "broken_job_link"
    OTHER = "other"


class ReportState(enum.StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class Application(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A job the user is pursuing. Linked to a GlideUp job when it came from the board,
    or entered by hand for jobs found elsewhere."""

    __tablename__ = "applications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="SET NULL")
    )
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000))
    location: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[ApplicationStatus] = mapped_column(
        _enum(ApplicationStatus, "application_status"), nullable=False
    )
    position: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )  # order in its column
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    salary: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)

    events: Mapped[list["ApplicationEvent"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="ApplicationEvent.created_at"
    )

    __table_args__ = (
        Index("ix_applications_user_status", "user_id", "status", "position"),
        # A board job is tracked once per user (manual entries have no job).
        Index(
            "uq_applications_user_job",
            "user_id",
            "job_id",
            unique=True,
            postgresql_where=text("job_id IS NOT NULL"),
            sqlite_where=text("job_id IS NOT NULL"),
        ),
    )


class ApplicationEvent(UUIDPrimaryKeyMixin, Base):
    """Timeline: created, status changes, notes."""

    __tablename__ = "application_events"

    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # created | status | note
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Reminder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reminders"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_reminders_due", "done", "emailed_at", "due_at"),)


class UserReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user telling us something is wrong (a question, AI feedback, a job link)."""

    __tablename__ = "user_reports"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    kind: Mapped[ReportKind] = mapped_column(_enum(ReportKind, "report_kind"), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(30))  # job | question | interview | ...
    target_id: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    page_url: Mapped[str | None] = mapped_column(String(500))
    state: Mapped[ReportState] = mapped_column(
        _enum(ReportState, "report_state"),
        default=ReportState.OPEN,
        server_default=ReportState.OPEN.value,
        nullable=False,
    )
    reply: Mapped[str | None] = mapped_column(Text)  # shown to the user
    handled_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    context: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    __table_args__ = (Index("ix_user_reports_state_created", "state", "created_at"),)
