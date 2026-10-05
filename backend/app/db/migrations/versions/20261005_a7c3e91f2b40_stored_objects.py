"""stored_objects: file bytes in Postgres (STORAGE_BACKEND=database).

Revision ID: a7c3e91f2b40
Revises: 0033a49e7d7d
Create Date: 2026-10-05 19:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e91f2b40"
down_revision: str | None = "0033a49e7d7d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stored_objects",
        sa.Column("bucket", sa.String(length=63), nullable=False),
        sa.Column("key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("bucket", "key", name=op.f("pk_stored_objects")),
    )


def downgrade() -> None:
    op.drop_table("stored_objects")
