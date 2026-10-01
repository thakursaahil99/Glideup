"""Company hiring signal on jobs: open roles and roles opened in the last 7 days.

Revision ID: 8b2d3f0a5c21
Revises: 7a1c2e9d4b10
Create Date: 2026-10-01 17:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8b2d3f0a5c21"
down_revision: str | None = "7a1c2e9d4b10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "jobs", sa.Column("company_open_roles", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "jobs", sa.Column("company_new_roles_7d", sa.Integer(), server_default="0", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("jobs", "company_new_roles_7d")
    op.drop_column("jobs", "company_open_roles")
