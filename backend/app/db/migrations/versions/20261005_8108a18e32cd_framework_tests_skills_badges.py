"""Framework tests (frameworks, attempts), skill scores and badges; question type content.

Revision ID: 8108a18e32cd
Revises: 5a647c5b42de
Create Date: 2026-10-05 16:15:18.128104
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8108a18e32cd"
down_revision: str | None = "5a647c5b42de"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "frameworks",
        sa.Column("key", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("language_key", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "composition",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("key", name=op.f("pk_frameworks")),
    )
    op.create_table(
        "framework_attempts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("framework_key", sa.String(length=30), nullable=False),
        sa.Column(
            "status",
            sa.Enum("in_progress", "grading", "graded", "failed", name="attempt_status"),
            server_default="in_progress",
            nullable=False,
        ),
        sa.Column(
            "question_ids",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "answers",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "results",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "sections",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("level", sa.String(length=15), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
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
            ["framework_key"],
            ["frameworks.key"],
            name=op.f("fk_framework_attempts_framework_key_frameworks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_framework_attempts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_framework_attempts")),
    )
    op.create_index(
        "ix_framework_attempts_user",
        "framework_attempts",
        ["user_id", "framework_key", "created_at"],
        unique=False,
    )
    op.create_table(
        "skill_scores",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("skill", sa.String(length=30), nullable=False),
        sa.Column("kind", sa.String(length=15), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=15), nullable=False),
        sa.Column(
            "evidence",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
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
            name=op.f("fk_skill_scores_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "skill", name=op.f("pk_skill_scores")),
    )
    op.create_table(
        "user_badges",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("badge", sa.String(length=50), nullable=False),
        sa.Column("awarded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "context",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_badges_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "badge", name=op.f("pk_user_badges")),
    )
    op.add_column("questions", sa.Column("framework_key", sa.String(length=30), nullable=True))
    op.add_column(
        "questions",
        sa.Column(
            "content",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_questions_framework_type", "questions", ["framework_key", "type"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_questions_framework_key_frameworks"),
        "questions",
        "frameworks",
        ["framework_key"],
        ["key"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_questions_framework_key_frameworks"), "questions", type_="foreignkey"
    )
    op.drop_index("ix_questions_framework_type", table_name="questions")
    op.drop_column("questions", "content")
    op.drop_column("questions", "framework_key")
    op.drop_table("user_badges")
    op.drop_table("skill_scores")
    op.drop_index("ix_framework_attempts_user", table_name="framework_attempts")
    op.drop_table("framework_attempts")
    op.drop_table("frameworks")
    sa.Enum(name="attempt_status").drop(op.get_bind(), checkfirst=True)
