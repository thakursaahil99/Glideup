"""Coding practice: languages, questions with tests, submissions, AI question generation."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.interview import Difficulty


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class QuestionStatus(enum.StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Verdict(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    ACCEPTED = "accepted"
    WRONG_ANSWER = "wrong_answer"
    COMPILE_ERROR = "compile_error"
    RUNTIME_ERROR = "runtime_error"
    TIME_LIMIT = "time_limit"
    MEMORY_LIMIT = "memory_limit"
    SANDBOX_ERROR = "sandbox_error"  # our side failed; not the user's fault


class GenerationStatus(enum.StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"  # generated and auto-validated; waiting for an admin
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class Language(TimestampMixin, Base):
    """A programming language users can solve in. Limits are admin-editable."""

    __tablename__ = "languages"

    key: Mapped[str] = mapped_column(String(20), primary_key=True)  # python, javascript, ...
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    time_limit_s: Mapped[float] = mapped_column(Float, nullable=False)
    memory_limit_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Question(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A DSA problem: read stdin, print stdout. Graded against visible and hidden tests."""

    __tablename__ = "questions"

    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # dsa | mcq | review | viva | project (the last four belong to a framework test)
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="dsa")
    framework_key: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("frameworks.key", ondelete="SET NULL")
    )
    # Type-specific data, validated by app.modules.skills.content (options + answer for
    # MCQ, the code and its planted issues for review, key points for viva, ...).
    content: Mapped[dict[str, Any] | None]
    difficulty: Mapped[Difficulty] = mapped_column(_enum(Difficulty, "difficulty"), nullable=False)
    topics: Mapped[list[str]] = mapped_column(default=list)
    statement: Mapped[str] = mapped_column(Text, nullable=False)  # Markdown
    status: Mapped[QuestionStatus] = mapped_column(
        _enum(QuestionStatus, "question_status"),
        default=QuestionStatus.DRAFT,
        server_default=QuestionStatus.DRAFT.value,
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="manual")  # | ai | seed
    # The last "run reference solutions" result: {"ok": bool, "at": iso, "details": [...]}.
    validation: Mapped[dict[str, Any] | None]
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )

    templates: Mapped[list["QuestionTemplate"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="QuestionTemplate.language_key"
    )
    tests: Mapped[list["TestCase"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="TestCase.position"
    )

    __table_args__ = (
        Index("ix_questions_status_difficulty", "status", "difficulty"),
        Index("ix_questions_framework_type", "framework_key", "type"),
    )


class QuestionTemplate(UUIDPrimaryKeyMixin, Base):
    """Starter code (what users see) and a reference solution (admins only) per language."""

    __tablename__ = "question_templates"

    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    language_key: Mapped[str] = mapped_column(
        String(20), ForeignKey("languages.key", ondelete="CASCADE"), nullable=False
    )
    starter_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reference_solution: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("uq_question_templates_lang", "question_id", "language_key", unique=True),
    )


class TestCase(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "test_cases"
    __test__ = False  # not a pytest class

    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_output: Mapped[str] = mapped_column(Text, nullable=False, default="")
    hidden: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class Submission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "submissions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    language_key: Mapped[str] = mapped_column(String(20), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[Verdict] = mapped_column(
        _enum(Verdict, "verdict"),
        default=Verdict.QUEUED,
        server_default=Verdict.QUEUED.value,
        nullable=False,
    )
    passed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Per test: {"position", "hidden", "verdict", "time_ms", "memory_kb", + details if visible}
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    compile_output: Mapped[str | None] = mapped_column(Text)
    max_time_ms: Mapped[int | None] = mapped_column(Integer)
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_submissions_user_question", "user_id", "question_id", "created_at"),
        Index(
            "uq_submissions_idempotency",
            "user_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
    )


class QuestionGeneration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An AI-written question waiting for review: generated, auto-validated by running its
    reference solution in the sandbox, then approved or rejected by an admin."""

    __tablename__ = "question_generation_queue"

    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    difficulty: Mapped[Difficulty] = mapped_column(_enum(Difficulty, "difficulty"), nullable=False)
    status: Mapped[GenerationStatus] = mapped_column(
        _enum(GenerationStatus, "generation_status"),
        default=GenerationStatus.PENDING,
        server_default=GenerationStatus.PENDING.value,
        nullable=False,
    )
    draft: Mapped[dict[str, Any] | None]  # the generated question, outputs filled by the sandbox
    validation: Mapped[dict[str, Any] | None]
    error: Mapped[str | None] = mapped_column(Text)
    generated_by: Mapped[str | None] = mapped_column(String(200))
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("questions.id", ondelete="SET NULL")
    )
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
