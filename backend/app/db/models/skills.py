"""Framework tests, skill scores and badges."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, Uuid, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class AttemptStatus(enum.StrEnum):
    IN_PROGRESS = "in_progress"
    GRADING = "grading"
    GRADED = "graded"
    FAILED = "failed"  # grading failed; can be retried


class Framework(TimestampMixin, Base):
    """A framework users can be tested on (React, FastAPI, ...). Admin-editable."""

    __tablename__ = "frameworks"

    key: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    language_key: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=40)
    # How many questions of each type a test draws: {"mcq": 6, "review": 1, ...}
    composition: Mapped[dict[str, Any]] = mapped_column(default=dict)


class FrameworkAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "framework_attempts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    framework_key: Mapped[str] = mapped_column(
        String(30), ForeignKey("frameworks.key", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[AttemptStatus] = mapped_column(
        Enum(AttemptStatus, name="attempt_status", values_callable=lambda e: [m.value for m in e]),
        default=AttemptStatus.IN_PROGRESS,
        server_default=AttemptStatus.IN_PROGRESS.value,
        nullable=False,
    )
    question_ids: Mapped[list[str]] = mapped_column(default=list)  # drawn at start, in order
    answers: Mapped[dict[str, Any]] = mapped_column(default=dict)  # question id -> answer
    # question id -> {"score": 0-1, "feedback", "details"}; plus per-type section scores
    results: Mapped[dict[str, Any]] = mapped_column(default=dict)
    sections: Mapped[dict[str, Any]] = mapped_column(default=dict)
    score: Mapped[int | None] = mapped_column(Integer)  # 0-100
    level: Mapped[str | None] = mapped_column(String(15))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_framework_attempts_user", "user_id", "framework_key", "created_at"),
    )


class SkillScore(TimestampMixin, Base):
    """A user's measured level in one skill (a framework or a language), from tests."""

    __tablename__ = "skill_scores"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    skill: Mapped[str] = mapped_column(String(30), primary_key=True)  # e.g. "react", "python"
    kind: Mapped[str] = mapped_column(String(15), nullable=False)  # framework | language
    score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-100, best so far
    level: Mapped[str] = mapped_column(String(15), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class UserBadge(Base):
    __tablename__ = "user_badges"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    badge: Mapped[str] = mapped_column(String(50), primary_key=True)
    awarded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
