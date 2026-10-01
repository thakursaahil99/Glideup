"""Add SmartRecruiters to the supported ATS boards.

Revision ID: 7a1c2e9d4b10
Revises: ce95e69b3af2
Create Date: 2026-10-01 17:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "7a1c2e9d4b10"
down_revision: str | None = "ce95e69b3af2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Adding an enum value is safe and instant in Postgres (no table rewrite).
    op.execute("ALTER TYPE ats ADD VALUE IF NOT EXISTS 'smartrecruiters'")


def downgrade() -> None:
    # Postgres cannot drop a single enum value. Remove the companies that use it, then
    # rebuild the type without it.
    op.execute("DELETE FROM companies WHERE ats = 'smartrecruiters'")
    op.execute("ALTER TYPE ats RENAME TO ats_old")
    op.execute("CREATE TYPE ats AS ENUM ('greenhouse', 'lever', 'ashby')")
    op.execute("ALTER TABLE companies ALTER COLUMN ats TYPE ats USING ats::text::ats")
    op.execute("DROP TYPE ats_old")
