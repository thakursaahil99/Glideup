"""Application tracker (applications, events), reminders and user reports.

Revision ID: 191d3541cc25
Revises: 8108a18e32cd
Create Date: 2026-10-05 16:34:53.636577
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "191d3541cc25"
down_revision: str | None = "8108a18e32cd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_reports",
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "kind",
            sa.Enum(
                "wrong_question", "bad_ai_feedback", "broken_job_link", "other", name="report_kind"
            ),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(length=30), nullable=True),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("page_url", sa.String(length=500), nullable=True),
        sa.Column(
            "state",
            sa.Enum("open", "resolved", "dismissed", name="report_state"),
            server_default="open",
            nullable=False,
        ),
        sa.Column("reply", sa.Text(), nullable=True),
        sa.Column("handled_by_id", sa.Uuid(), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "context",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
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
            ["handled_by_id"],
            ["users.id"],
            name=op.f("fk_user_reports_handled_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_reports_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_reports")),
    )
    op.create_index(
        "ix_user_reports_state_created", "user_reports", ["state", "created_at"], unique=False
    )
    op.create_table(
        "applications",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("company", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("location", sa.String(length=300), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "saved",
                "applied",
                "screening",
                "interviewing",
                "offer",
                "rejected",
                "withdrawn",
                name="application_status",
            ),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("salary", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            ["job_id"], ["jobs.id"], name=op.f("fk_applications_job_id_jobs"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_applications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
    )
    op.create_index(
        "ix_applications_user_status",
        "applications",
        ["user_id", "status", "position"],
        unique=False,
    )
    op.create_index(
        "uq_applications_user_job",
        "applications",
        ["user_id", "job_id"],
        unique=True,
        postgresql_where=sa.text("job_id IS NOT NULL"),
        sqlite_where=sa.text("job_id IS NOT NULL"),
    )
    op.create_table(
        "application_events",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_application_events_application_id_applications"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_events")),
    )
    op.create_table(
        "reminders",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("done", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("emailed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_reminders_application_id_applications"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_reminders_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminders")),
    )
    op.create_index("ix_reminders_due", "reminders", ["done", "emailed_at", "due_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_reminders_due", table_name="reminders")
    op.drop_table("reminders")
    op.drop_table("application_events")
    op.drop_index(
        "uq_applications_user_job",
        table_name="applications",
        postgresql_where=sa.text("job_id IS NOT NULL"),
        sqlite_where=sa.text("job_id IS NOT NULL"),
    )
    op.drop_index("ix_applications_user_status", table_name="applications")
    op.drop_table("applications")
    op.drop_index("ix_user_reports_state_created", table_name="user_reports")
    op.drop_table("user_reports")
    for name in ("report_state", "report_kind", "application_status"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
