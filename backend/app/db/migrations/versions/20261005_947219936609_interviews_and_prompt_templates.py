"""Mock interviews (types, interviews, messages, reports) and versioned prompt templates.

Revision ID: 947219936609
Revises: c96a585c0aca
Create Date: 2026-10-05 11:08:04.214957
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "947219936609"
down_revision: str | None = "c96a585c0aca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_types",
        sa.Column("key", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("max_followups", sa.Integer(), nullable=False),
        sa.Column(
            "difficulty", sa.Enum("easy", "medium", "hard", name="difficulty"), nullable=False
        ),
        sa.Column(
            "rubric",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("key", name=op.f("pk_interview_types")),
    )
    op.create_table(
        "prompt_templates",
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("active_version", sa.Integer(), nullable=True),
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
        sa.PrimaryKeyConstraint("name", name=op.f("pk_prompt_templates")),
    )
    op.create_table(
        "prompt_template_versions",
        sa.Column("template_name", sa.String(length=50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("system", sa.Text(), nullable=False),
        sa.Column("user", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_prompt_template_versions_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["template_name"],
            ["prompt_templates.name"],
            name=op.f("fk_prompt_template_versions_template_name_prompt_templates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prompt_template_versions")),
    )
    op.create_index(
        "uq_prompt_versions_name_version",
        "prompt_template_versions",
        ["template_name", "version"],
        unique=True,
    )
    op.create_table(
        "interviews",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type_key", sa.String(length=30), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("resume_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "preparing", "ready", "in_progress", "completed", "failed", name="interview_status"
            ),
            nullable=False,
        ),
        sa.Column(
            "difficulty", sa.Enum("easy", "medium", "hard", name="difficulty"), nullable=False
        ),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("max_followups", sa.Integer(), nullable=False),
        sa.Column(
            "rubric",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "plan",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("job_title", sa.String(length=300), nullable=True),
        sa.Column("company_name", sa.String(length=200), nullable=True),
        sa.Column("current_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("followups_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("hints_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.String(length=20), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("ws_ticket_jti", sa.Uuid(), nullable=True),
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
            ["job_id"], ["jobs.id"], name=op.f("fk_interviews_job_id_jobs"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["resume_id"],
            ["resumes.id"],
            name=op.f("fk_interviews_resume_id_resumes"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["type_key"],
            ["interview_types.key"],
            name=op.f("fk_interviews_type_key_interview_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_interviews_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interviews")),
    )
    op.create_index("ix_interviews_status_ends", "interviews", ["status", "ends_at"], unique=False)
    op.create_index(
        "ix_interviews_user_created", "interviews", ["user_id", "created_at"], unique=False
    )
    op.create_table(
        "interview_messages",
        sa.Column("interview_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=15), nullable=False),
        sa.Column("kind", sa.String(length=15), nullable=False),
        sa.Column("question_index", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("attachment", sa.Text(), nullable=True),
        sa.Column("client_id", sa.String(length=64), nullable=True),
        sa.Column("interrupted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            name=op.f("fk_interview_messages_interview_id_interviews"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interview_messages")),
    )
    op.create_index(
        "uq_interview_messages_client",
        "interview_messages",
        ["interview_id", "client_id"],
        unique=True,
        postgresql_where=sa.text("client_id IS NOT NULL"),
        sqlite_where=sa.text("client_id IS NOT NULL"),
    )
    op.create_index(
        "uq_interview_messages_seq", "interview_messages", ["interview_id", "seq"], unique=True
    )
    op.create_table(
        "interview_reports",
        sa.Column("interview_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "generating", "done", "failed", "skipped", name="report_status"),
            nullable=False,
        ),
        sa.Column("overall_score", sa.Integer(), nullable=True),
        sa.Column(
            "result",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("prompt_version", sa.String(length=50), nullable=True),
        sa.Column("generated_by", sa.String(length=200), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
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
            ["interview_id"],
            ["interviews.id"],
            name=op.f("fk_interview_reports_interview_id_interviews"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("interview_id", name=op.f("pk_interview_reports")),
    )


def downgrade() -> None:
    op.drop_table("interview_reports")
    op.drop_index("uq_interview_messages_seq", table_name="interview_messages")
    op.drop_index(
        "uq_interview_messages_client",
        table_name="interview_messages",
        postgresql_where=sa.text("client_id IS NOT NULL"),
        sqlite_where=sa.text("client_id IS NOT NULL"),
    )
    op.drop_table("interview_messages")
    op.drop_index("ix_interviews_user_created", table_name="interviews")
    op.drop_index("ix_interviews_status_ends", table_name="interviews")
    op.drop_table("interviews")
    op.drop_index("uq_prompt_versions_name_version", table_name="prompt_template_versions")
    op.drop_table("prompt_template_versions")
    op.drop_table("prompt_templates")
    op.drop_table("interview_types")
    for name in ("report_status", "interview_status", "difficulty"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
