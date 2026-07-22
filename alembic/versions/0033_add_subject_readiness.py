"""add subject readiness quiz tables

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-21 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "directions",
        sa.Column(
            "subjects_required",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.drop_column("directions", "subjects_to_develop")

    subject_question_kind_enum = postgresql.ENUM(
        "level", "interest", name="subject_question_kind_enum"
    )

    op.create_table(
        "subject_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject", sa.String(100), nullable=False),
        sa.Column("kind", subject_question_kind_enum, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subject", "kind", name="uq_subject_question_subject_kind"),
    )
    op.create_index("ix_subject_questions_subject", "subject_questions", ["subject"])

    subject_readiness_status_enum = postgresql.ENUM(
        "in_progress", "completed", name="subject_readiness_status_enum"
    )

    op.create_table(
        "subject_readiness_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("direction_slug", sa.String(100), nullable=False),
        sa.Column("question_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("answers", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("subject_scores", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", subject_readiness_status_enum, nullable=False, server_default="in_progress"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_id"),
    )


def downgrade() -> None:
    op.drop_table("subject_readiness_sessions")
    op.execute("DROP TYPE IF EXISTS subject_readiness_status_enum")

    op.drop_index("ix_subject_questions_subject", table_name="subject_questions")
    op.drop_table("subject_questions")
    op.execute("DROP TYPE IF EXISTS subject_question_kind_enum")

    op.add_column(
        "directions",
        sa.Column("subjects_to_develop", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.drop_column("directions", "subjects_required")
