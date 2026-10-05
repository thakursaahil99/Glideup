"""Platform controls managed from the admin console: feature flags, settings, announcements."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class FeatureFlag(TimestampMixin, Base):
    """Turn a feature on/off globally, for a percentage of users, or for named users."""

    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # 0-100: when enabled, the share of users (stable per user) who get it.
    rollout_percent: Mapped[int] = mapped_column(Integer, default=100, server_default="100")
    # Always on for these users (testers), even when the flag is off.
    allow_user_ids: Mapped[list[str]] = mapped_column(default=list)


class SiteSetting(TimestampMixin, Base):
    """Admin-editable runtime settings (LLM routing, cache, budgets...), JSON values."""

    __tablename__ = "site_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONType, nullable=True)


class Announcement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "announcements"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    level: Mapped[str] = mapped_column(String(10), nullable=False, default="info")  # info|warning
    audience: Mapped[str] = mapped_column(String(10), nullable=False, default="all")  # all|admins
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    extra: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    __table_args__ = (Index("ix_announcements_active", "active", "starts_at", "ends_at"),)
