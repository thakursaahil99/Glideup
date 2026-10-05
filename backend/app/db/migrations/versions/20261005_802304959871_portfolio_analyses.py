"""Portfolio analyses: skills and projects found on GitHub or a portfolio site.

Revision ID: 802304959871
Revises: 8b2d3f0a5c21
Create Date: 2026-10-05 10:26:04.741829
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "802304959871"
down_revision: str | None = "8b2d3f0a5c21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portfolio_analyses",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Enum("github", "website", name="portfolio_kind"), nullable=False),
        sa.Column("url", sa.String(length=300), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "analyzing", "done", "failed", name="analysis_status"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "result",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("analyzed_by", sa.String(length=200), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_portfolio_analyses_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_analyses")),
    )
    op.create_index(
        "uq_portfolio_analyses_user_kind", "portfolio_analyses", ["user_id", "kind"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_portfolio_analyses_user_kind", table_name="portfolio_analyses")
    op.drop_table("portfolio_analyses")
    sa.Enum(name="analysis_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="portfolio_kind").drop(op.get_bind(), checkfirst=True)
