"""File bytes kept in Postgres, for hosts without object storage or a persistent disk."""

from sqlalchemy import LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class StoredObject(TimestampMixin, Base):
    __tablename__ = "stored_objects"

    bucket: Mapped[str] = mapped_column(String(63), primary_key=True)
    key: Mapped[str] = mapped_column(String(500), primary_key=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
