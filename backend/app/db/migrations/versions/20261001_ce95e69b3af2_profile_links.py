"""Profile links: portfolio, LinkedIn and GitHub URLs.

Revision ID: ce95e69b3af2
Revises: 5210de109c55
Create Date: 2026-10-01 16:00:48.369062
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ce95e69b3af2"
down_revision: str | None = "5210de109c55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("portfolio_url", sa.String(length=300), nullable=True))
    op.add_column("profiles", sa.Column("linkedin_url", sa.String(length=300), nullable=True))
    op.add_column("profiles", sa.Column("github_url", sa.String(length=300), nullable=True))


def downgrade() -> None:
    op.drop_column("profiles", "github_url")
    op.drop_column("profiles", "linkedin_url")
    op.drop_column("profiles", "portfolio_url")
