"""Profiles, resumes (+ skills, pgvector embedding) and LLM usage log.

Revision ID: 45d582700871
Revises: 088a2df3fd5f
Create Date: 2026-10-01 11:40:25.291976
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "45d582700871"
down_revision: str | None = "088a2df3fd5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_usage",
        sa.Column("task", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_llm_usage_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_usage")),
    )
    op.create_index("ix_llm_usage_created_at", "llm_usage", ["created_at"], unique=False)
    op.create_index("ix_llm_usage_provider_model", "llm_usage", ["provider", "model"], unique=False)
    op.create_index("ix_llm_usage_task", "llm_usage", ["task"], unique=False)
    op.create_table(
        "profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("headline", sa.String(length=200), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("years_experience", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column(
            "target_roles",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "preferred_locations",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "remote_preference",
            sa.Enum("remote", "hybrid", "onsite", "any", name="remote_preference"),
            server_default="any",
            nullable=False,
        ),
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["user_id"], ["users.id"], name=op.f("fk_profiles_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_profiles")),
    )
    op.create_table(
        "resumes",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("uploaded", "parsing", "parsed", "failed", name="resume_status"),
            server_default="uploaded",
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("parse_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column(
            "parsed",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("parsed_by", sa.String(length=200), nullable=True),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.vector.VECTOR(dim=768).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column("embedding_model", sa.String(length=200), nullable=True),
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
            ["user_id"], ["users.id"], name=op.f("fk_resumes_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resumes")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_resumes_storage_key")),
    )
    op.create_index(
        "ix_resumes_user_id_created_at", "resumes", ["user_id", "created_at"], unique=False
    )
    op.create_index(
        "uq_resumes_one_active_per_user",
        "resumes",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
        sqlite_where=sa.text("is_active"),
    )
    op.create_table(
        "resume_skills",
        sa.Column("resume_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("normalized", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("years", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("level", sa.String(length=20), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["resume_id"],
            ["resumes.id"],
            name=op.f("fk_resume_skills_resume_id_resumes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resume_skills")),
    )
    op.create_index("ix_resume_skills_normalized", "resume_skills", ["normalized"], unique=False)
    op.create_index(
        "uq_resume_skills_resume_normalized",
        "resume_skills",
        ["resume_id", "normalized"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_resume_skills_resume_normalized", table_name="resume_skills")
    op.drop_index("ix_resume_skills_normalized", table_name="resume_skills")
    op.drop_table("resume_skills")
    op.drop_index(
        "uq_resumes_one_active_per_user",
        table_name="resumes",
        postgresql_where=sa.text("is_active"),
        sqlite_where=sa.text("is_active"),
    )
    op.drop_index("ix_resumes_user_id_created_at", table_name="resumes")
    op.drop_table("resumes")
    op.drop_table("profiles")
    op.drop_index("ix_llm_usage_task", table_name="llm_usage")
    op.drop_index("ix_llm_usage_provider_model", table_name="llm_usage")
    op.drop_index("ix_llm_usage_created_at", table_name="llm_usage")
    op.drop_table("llm_usage")
    sa.Enum(name="resume_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="remote_preference").drop(op.get_bind(), checkfirst=True)
