"""direction_roadmaps: add program_id index and program_fit

Stores the optional LLM-derived subject-fit summary for the program a
direction roadmap was generated against. `program_id` itself is already
added by a3f9c1d84e02 (a sibling branch merged into this history); this
revision only indexes it and adds program_fit. The existing
`(assessment_id, direction_slug)` uniqueness stays unchanged: there is
still one roadmap row per direction, and regenerating with another
program rewrites the same row.

Revision ID: 0043
Revises: a3f9c1d84e02
Create Date: 2026-08-18 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0043"
down_revision: str | None = "a3f9c1d84e02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
