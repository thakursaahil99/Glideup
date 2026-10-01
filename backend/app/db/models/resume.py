import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# nomic-embed-text produces 768-dim vectors. Changing the embedding model to one with a
# different size needs a migration (and a re-embed job), so the size is fixed here.
EMBEDDING_DIMENSIONS = 768

# pgvector on Postgres; JSON on SQLite so the unit-test database can hold the same values.
EmbeddingType = Vector(EMBEDDING_DIMENSIONS).with_variant(JSON(), "sqlite")


class ResumeStatus(enum.StrEnum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    FAILED = "failed"


class Resume(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "resumes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # The newest successfully uploaded resume is the one used for matching.
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[ResumeStatus] = mapped_column(
        Enum(ResumeStatus, name="resume_status", values_callable=lambda e: [m.value for m in e]),
        default=ResumeStatus.UPLOADED,
        server_default=ResumeStatus.UPLOADED.value,
        nullable=False,
    )
    error: Mapped[str | None] = mapped_column(Text)
    parse_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    raw_text: Mapped[str | None] = mapped_column(Text)
    # Validated `ParsedResume` JSON. Edited by the user after parsing.
    parsed: Mapped[dict[str, Any] | None]
    parsed_by: Mapped[str | None] = mapped_column(String(200))  # "provider:model"
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingType)
    embedding_model: Mapped[str | None] = mapped_column(String(200))

    skills: Mapped[list["ResumeSkill"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ResumeSkill.name",
    )

    __table_args__ = (
        Index("ix_resumes_user_id_created_at", "user_id", "created_at"),
        # At most one active resume per user.
        Index(
            "uq_resumes_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active"),
        ),
    )


class ResumeSkill(UUIDPrimaryKeyMixin, Base):
    """Skills extracted from a resume, normalised for matching (Phase 4)."""

    __tablename__ = "resume_skills"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # display name
    normalized: Mapped[str] = mapped_column(String(100), nullable=False)  # lower-case key
    category: Mapped[str | None] = mapped_column(String(50))
    years: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    level: Mapped[str | None] = mapped_column(String(20))

    resume: Mapped[Resume] = relationship(back_populates="skills")

    __table_args__ = (
        Index("uq_resume_skills_resume_normalized", "resume_id", "normalized", unique=True),
        Index("ix_resume_skills_normalized", "normalized"),
    )
