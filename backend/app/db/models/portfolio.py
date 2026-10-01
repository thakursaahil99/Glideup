import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PortfolioKind(enum.StrEnum):
    GITHUB = "github"  # read through GitHub's public REST API
    WEBSITE = "website"  # a personal site: fetched (SSRF-safe) and parsed by the LLM


class AnalysisStatus(enum.StrEnum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    DONE = "done"
    FAILED = "failed"


class PortfolioAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Skills and projects found in a user's GitHub or portfolio site.

    One row per (user, kind): analyzing a new GitHub URL replaces the old analysis.
    Skills live in `result` (a validated `PortfolioResult`) and are merged with resume
    skills when matching (see `app.modules.portfolio.service.user_skills`).
    """

    __tablename__ = "portfolio_analyses"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[PortfolioKind] = mapped_column(
        Enum(PortfolioKind, name="portfolio_kind", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[AnalysisStatus] = mapped_column(
        Enum(
            AnalysisStatus, name="analysis_status", values_callable=lambda e: [m.value for m in e]
        ),
        default=AnalysisStatus.PENDING,
        server_default=AnalysisStatus.PENDING.value,
        nullable=False,
    )
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    result: Mapped[dict[str, Any] | None]
    analyzed_by: Mapped[str | None] = mapped_column(String(200))  # "github-api" / "provider:model"
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("uq_portfolio_analyses_user_kind", "user_id", "kind", unique=True),)
