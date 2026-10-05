"""Job embeddings (pgvector + HNSW) and stored AI skill-gap analyses (job_matches).

Revision ID: c96a585c0aca
Revises: 802304959871
Create Date: 2026-10-05 10:27:51.919826
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c96a585c0aca"
down_revision: str | None = "802304959871"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_matches",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("resume_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "analyzing", "done", "failed", name="match_analysis_status"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column(
            "analysis",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("job_content_hash", sa.String(length=64), nullable=False),
        sa.Column("skills_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("analyzed_by", sa.String(length=200), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
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
            ["job_id"], ["jobs.id"], name=op.f("fk_job_matches_job_id_jobs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["resume_id"],
            ["resumes.id"],
            name=op.f("fk_job_matches_resume_id_resumes"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_job_matches_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_matches")),
    )
    op.create_index(
        "ix_job_matches_user_requested", "job_matches", ["user_id", "requested_at"], unique=False
    )
    op.create_index("uq_job_matches_user_job", "job_matches", ["user_id", "job_id"], unique=True)
    op.add_column(
        "jobs",
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.vector.VECTOR(dim=768).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
    )
    op.add_column("jobs", sa.Column("embedding_model", sa.String(length=200), nullable=True))
    op.add_column("jobs", sa.Column("embedded_hash", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_jobs_embedding_hnsw",
        "jobs",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_where=sa.text("embedding IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_jobs_embedding_hnsw",
        table_name="jobs",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_where=sa.text("embedding IS NOT NULL"),
    )
    op.drop_column("jobs", "embedded_hash")
    op.drop_column("jobs", "embedding_model")
    op.drop_column("jobs", "embedding")
    op.drop_index("uq_job_matches_user_job", table_name="job_matches")
    op.drop_index("ix_job_matches_user_requested", table_name="job_matches")
    op.drop_table("job_matches")
    sa.Enum(name="match_analysis_status").drop(op.get_bind(), checkfirst=True)
