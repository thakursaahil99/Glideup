import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class ATS(enum.StrEnum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"


class WorkMode(enum.StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class ExperienceLevel(enum.StrEnum):
    INTERNSHIP = "internship"
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"  # staff / principal / distinguished
    MANAGER = "manager"
    UNKNOWN = "unknown"


class RunStatus(enum.StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"  # some boards failed; their jobs were left untouched
    FAILED = "failed"


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A company whose public ATS job board we read (Greenhouse / Lever / Ashby)."""

    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    ats: Mapped[ATS] = mapped_column(_enum(ATS, "ats"), nullable=False)
    board_token: Mapped[str] = mapped_column(String(100), nullable=False)
    website: Mapped[str | None] = mapped_column(String(300))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    active_jobs: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    __table_args__ = (UniqueConstraint("ats", "board_token", name="uq_companies_ats_board"),)


class JobSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One configured source plugin, managed from the admin console."""

    __tablename__ = "job_sources"

    key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)  # = plugin key
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    schedule_minutes: Mapped[int] = mapped_column(Integer, default=360, server_default="360")
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=60, server_default="60")
    # Plugin-specific settings (e.g. Adzuna countries and search terms).
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    active_jobs: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class IngestionRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ingestion_runs"

    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("job_sources.id", ondelete="CASCADE"), nullable=False
    )
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)  # schedule | manual
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[RunStatus] = mapped_column(
        _enum(RunStatus, "run_status"), default=RunStatus.RUNNING, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    deactivated: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list[str]] = mapped_column(default=list)

    __table_args__ = (Index("ix_ingestion_runs_source_started", "source_id", "started_at"),)


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "jobs"

    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("job_sources.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="SET NULL")
    )
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    # Stale detection is per scope (one ATS board, or one aggregator query), so a board that
    # failed to fetch never has its jobs wrongly marked inactive.
    scope: Mapped[str] = mapped_column(String(200), nullable=False)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str | None] = mapped_column(String(300))  # as published by the source
    country: Mapped[str | None] = mapped_column(String(2))  # primary country (ISO 3166-1)
    # Structured location parsed from `location` (a job can list several places).
    countries: Mapped[list[str]] = mapped_column(default=list, server_default="[]")
    states: Mapped[list[str]] = mapped_column(default=list, server_default="[]")
    cities: Mapped[list[str]] = mapped_column(default=list, server_default="[]")
    # For remote jobs: "country" (restricted to `countries`) or "worldwide". None if not remote.
    remote_scope: Mapped[str | None] = mapped_column(String(10))
    # "|c:IN|s:Karnataka|ci:Bengaluru|" for exact filtering in the database search fallback.
    location_index: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    work_mode: Mapped[WorkMode] = mapped_column(
        _enum(WorkMode, "work_mode"), default=WorkMode.UNKNOWN, nullable=False
    )
    experience_level: Mapped[ExperienceLevel] = mapped_column(
        _enum(ExperienceLevel, "experience_level"), default=ExperienceLevel.UNKNOWN, nullable=False
    )
    employment_type: Mapped[str | None] = mapped_column(String(50))
    department: Mapped[str | None] = mapped_column(String(200))
    description_html: Mapped[str] = mapped_column(Text, nullable=False, default="")  # sanitised
    description_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    apply_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    salary_period: Mapped[str | None] = mapped_column(String(10))  # year | month | hour
    skills: Mapped[list[str]] = mapped_column(default=list)
    # "|python|react|" — portable exact-token filtering for the database search fallback.
    skills_index: Mapped[str] = mapped_column(Text, nullable=False, default="")

    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dedup_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="SET NULL")
    )
    # An admin confirmed this is NOT a duplicate; ingestion must not flag it again.
    dedup_override: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    source: Mapped[JobSource] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_jobs_source_external"),
        Index("ix_jobs_dedup_hash", "dedup_hash"),
        Index("ix_jobs_scope", "source_id", "scope"),
        Index("ix_jobs_listing", "is_active", "posted_at"),
        Index("ix_jobs_company_id", "company_id"),
        Index("ix_jobs_duplicate_of_id", "duplicate_of_id"),
    )

    @property
    def is_listed(self) -> bool:
        """Visible to job seekers (and present in the search index)."""
        return self.is_active and not self.is_hidden and self.duplicate_of_id is None


class SavedJob(Base):
    __tablename__ = "saved_jobs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped[Job] = relationship(lazy="joined")

    __table_args__ = (Index("ix_saved_jobs_user_created", "user_id", "created_at"),)
