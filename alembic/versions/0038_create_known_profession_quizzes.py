"""create known profession quizzes and logs

Revision ID: 0038
Revises: 0037
Create Date: 2026-07-27 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "known_profession_quizzes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("leaf_slug", sa.String(length=100), nullable=False),
        sa.Column("questions", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index("ix_known_profession_quizzes_leaf_slug", "known_profession_quizzes", ["leaf_slug"], unique=True)

    op.create_table(
        "known_profession_quiz_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("leaf_slug", sa.String(length=100), nullable=False),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("percent", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index("ix_known_profession_quiz_logs_assessment_id", "known_profession_quiz_logs", ["assessment_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_known_profession_quiz_logs_assessment_id", table_name="known_profession_quiz_logs")
    op.drop_table("known_profession_quiz_logs")
    op.drop_index("ix_known_profession_quizzes_leaf_slug", table_name="known_profession_quizzes")
    op.drop_table("known_profession_quizzes")
