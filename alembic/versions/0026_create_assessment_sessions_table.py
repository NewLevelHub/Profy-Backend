"""create assessment_sessions table

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-15 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive: a new 1:1 table next to `assessments`. A row's existence marks
    # that assessment as running on the new axis-driven engine (dual-run,
    # AKN-020) — Assessment.current_block/status keep working untouched.
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE assessment_session_status_enum AS ENUM (
                'in_progress', 'converged_single', 'converged_cluster', 'exhausted_ceiling'
            );
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.create_table(
        "assessment_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("belief", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("asked_question_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("asked_axis_families", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("step", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "status",
            postgresql.ENUM(
                "in_progress", "converged_single", "converged_cluster", "exhausted_ceiling",
                name="assessment_session_status_enum", create_type=False,
            ),
            nullable=False,
            server_default="in_progress",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_id"),
    )


def downgrade() -> None:
    op.drop_table("assessment_sessions")
    op.execute("DROP TYPE IF EXISTS assessment_session_status_enum;")
