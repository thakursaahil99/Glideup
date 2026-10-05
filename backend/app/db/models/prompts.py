import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PromptTemplate(TimestampMixin, Base):
    """An LLM prompt, editable from the admin console. The repository's template files
    are imported as the first versions and remain the fallback if the database is empty."""

    __tablename__ = "prompt_templates"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g. "interviewer"
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    active_version: Mapped[int | None] = mapped_column(Integer)


class PromptTemplateVersion(UUIDPrimaryKeyMixin, Base):
    """Immutable: editing a prompt creates a new version; rollback re-activates an old one."""

    __tablename__ = "prompt_template_versions"

    template_name: Mapped[str] = mapped_column(
        String(50), ForeignKey("prompt_templates.name", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    system: Mapped[str] = mapped_column(Text, nullable=False, default="")
    user: Mapped[str] = mapped_column(Text, nullable=False, default="")
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10), nullable=False)  # file | admin
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("uq_prompt_versions_name_version", "template_name", "version", unique=True),
    )
