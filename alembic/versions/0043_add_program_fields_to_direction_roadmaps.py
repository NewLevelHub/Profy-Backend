"""direction_roadmaps: add program_id and program_fit

Stores which concrete university program a direction roadmap was generated
against, plus the optional LLM-derived subject-fit summary for that program.
The existing `(assessment_id, direction_slug)` uniqueness stays unchanged:
there is still one roadmap row per direction, and regenerating with another
program rewrites the same row.

Revision ID: 0043
Revises: 0042
Create Date: 2026-08-18 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "direction_roadmaps",
        sa.Column(
            "program_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("programs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_direction_roadmaps_program_id",
        "direction_roadmaps",
        ["program_id"],
    )
    op.add_column(
        "direction_roadmaps",
        sa.Column("program_fit", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("direction_roadmaps", "program_fit")
    op.drop_index("ix_direction_roadmaps_program_id", table_name="direction_roadmaps")
    op.drop_column("direction_roadmaps", "program_id")
