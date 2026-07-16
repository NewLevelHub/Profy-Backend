"""create akinator_answer_logs table and feedback columns on assessment_sessions

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-15 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Purely additive: an append-only history table next to
    # assessment_sessions (which only tracks current state), plus a
    # feedback point on the session itself.
    op.create_table(
        "akinator_answer_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("selected_option_index", sa.Integer(), nullable=True),
        sa.Column("belief_after", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["session_id"], ["assessment_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["akinator_questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_akinator_answer_logs_session_id", "akinator_answer_logs", ["session_id"]
    )

    op.add_column("assessment_sessions", sa.Column("liked", sa.Boolean(), nullable=True))
    op.add_column("assessment_sessions", sa.Column("feedback_note", sa.Text(), nullable=True))
    op.add_column(
        "assessment_sessions", sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("assessment_sessions", "feedback_at")
    op.drop_column("assessment_sessions", "feedback_note")
    op.drop_column("assessment_sessions", "liked")
    op.drop_index("ix_akinator_answer_logs_session_id", table_name="akinator_answer_logs")
    op.drop_table("akinator_answer_logs")
