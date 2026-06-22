"""create assessments table

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-22 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE assessment_goal_enum AS ENUM ('explore', 'profession', 'university');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE assessment_status_enum AS ENUM ('in_progress', 'completed');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.create_table(
        "assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "goal",
            postgresql.ENUM("explore", "profession", "university", name="assessment_goal_enum", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM("in_progress", "completed", name="assessment_status_enum", create_type=False),
            nullable=False,
            server_default="in_progress",
        ),
        sa.Column("current_block", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assessments_profile_id", "assessments", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_assessments_profile_id", table_name="assessments")
    op.drop_table("assessments")
    op.execute("DROP TYPE IF EXISTS assessment_goal_enum;")
    op.execute("DROP TYPE IF EXISTS assessment_status_enum;")
