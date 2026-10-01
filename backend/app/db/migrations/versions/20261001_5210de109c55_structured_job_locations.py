"""Structured job locations: countries, states, cities, remote scope.

Existing jobs get empty values here and are re-parsed on their next ingestion run
(NORMALIZER_VERSION 3 changes every posting hash).

Revision ID: 5210de109c55
Revises: 4b81b945f73d
Create Date: 2026-10-01 15:40:34.548596
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5210de109c55"
down_revision: str | None = "4b81b945f73d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "countries",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "states",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "cities",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column("jobs", sa.Column("remote_scope", sa.String(length=10), nullable=True))
    op.add_column(
        "jobs", sa.Column("location_index", sa.Text(), nullable=False, server_default="")
    )


def downgrade() -> None:
    op.drop_column("jobs", "location_index")
    op.drop_column("jobs", "remote_scope")
    op.drop_column("jobs", "cities")
    op.drop_column("jobs", "states")
    op.drop_column("jobs", "countries")
