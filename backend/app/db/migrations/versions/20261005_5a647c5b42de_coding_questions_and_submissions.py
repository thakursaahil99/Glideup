"""Coding practice: languages, questions, templates, tests, submissions, AI generation queue.

Revision ID: 5a647c5b42de
Revises: 947219936609
Create Date: 2026-10-05 15:33:27.877697
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5a647c5b42de"
down_revision: str | None = "947219936609"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "languages",
        sa.Column("key", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("time_limit_s", sa.Float(), nullable=False),
        sa.Column("memory_limit_mb", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
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
        sa.PrimaryKeyConstraint("key", name=op.f("pk_languages")),
    )
    op.create_table(
        "questions",
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column(
            "difficulty", postgresql.ENUM("easy", "medium", "hard", name="difficulty", create_type=False), nullable=False
        ),
        sa.Column(
            "topics",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "published", "archived", name="question_status"),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column(
            "validation",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
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
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_questions_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_questions")),
        sa.UniqueConstraint("slug", name=op.f("uq_questions_slug")),
    )
    op.create_index(
        "ix_questions_status_difficulty", "questions", ["status", "difficulty"], unique=False
    )
    op.create_table(
        "question_generation_queue",
        sa.Column("topic", sa.String(length=100), nullable=False),
        sa.Column(
            "difficulty", postgresql.ENUM("easy", "medium", "hard", name="difficulty", create_type=False), nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "generating",
                "ready",
                "approved",
                "rejected",
                "failed",
                name="generation_status",
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "draft",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "validation",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("generated_by", sa.String(length=200), nullable=True),
        sa.Column("requested_by_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=True),
        sa.Column("question_id", sa.Uuid(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_question_generation_queue_question_id_questions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"],
            ["users.id"],
            name=op.f("fk_question_generation_queue_requested_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"],
            ["users.id"],
            name=op.f("fk_question_generation_queue_reviewed_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_generation_queue")),
    )
    op.create_table(
        "question_templates",
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("language_key", sa.String(length=20), nullable=False),
        sa.Column("starter_code", sa.Text(), nullable=False),
        sa.Column("reference_solution", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["language_key"],
            ["languages.key"],
            name=op.f("fk_question_templates_language_key_languages"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_question_templates_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_templates")),
    )
    op.create_index(
        "uq_question_templates_lang",
        "question_templates",
        ["question_id", "language_key"],
        unique=True,
    )
    op.create_table(
        "submissions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("language_key", sa.String(length=20), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column(
            "verdict",
            sa.Enum(
                "queued",
                "running",
                "accepted",
                "wrong_answer",
                "compile_error",
                "runtime_error",
                "time_limit",
                "memory_limit",
                "sandbox_error",
                name="verdict",
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("passed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "results",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("compile_output", sa.Text(), nullable=True),
        sa.Column("max_time_ms", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_submissions_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_submissions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submissions")),
    )
    op.create_index(
        "ix_submissions_user_question",
        "submissions",
        ["user_id", "question_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_submissions_idempotency",
        "submissions",
        ["user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_table(
        "test_cases",
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=False),
        sa.Column("hidden", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_test_cases_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_test_cases")),
    )


def downgrade() -> None:
    op.drop_table("test_cases")
    op.drop_index(
        "uq_submissions_idempotency",
        table_name="submissions",
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.drop_index("ix_submissions_user_question", table_name="submissions")
    op.drop_table("submissions")
    op.drop_index("uq_question_templates_lang", table_name="question_templates")
    op.drop_table("question_templates")
    op.drop_table("question_generation_queue")
    op.drop_index("ix_questions_status_difficulty", table_name="questions")
    op.drop_table("questions")
    op.drop_table("languages")
    for name in ("generation_status", "verdict", "question_status"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
