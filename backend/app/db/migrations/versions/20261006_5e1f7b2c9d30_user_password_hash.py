"""users.password_hash: email + password accounts.

Revision ID: 5e1f7b2c9d30
Revises: a7c3e91f2b40
Create Date: 2026-10-06 10:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5e1f7b2c9d30"
down_revision: str | None = "a7c3e91f2b40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_hash")
