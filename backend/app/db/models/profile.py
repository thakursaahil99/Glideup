import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class RemotePreference(enum.StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    ANY = "any"


class Profile(TimestampMixin, Base):
    """Career preferences. One row per user, created lazily on first read/write."""

    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    headline: Mapped[str | None] = mapped_column(String(200))
    bio: Mapped[str | None] = mapped_column(Text)
    years_experience: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    target_roles: Mapped[list[str]] = mapped_column(default=list)
    preferred_locations: Mapped[list[str]] = mapped_column(default=list)
    remote_preference: Mapped[RemotePreference] = mapped_column(
        Enum(
            RemotePreference,
            name="remote_preference",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=RemotePreference.ANY,
        server_default=RemotePreference.ANY.value,
        nullable=False,
    )
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
