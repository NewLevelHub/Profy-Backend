"""redesign direction roadmap: real facts + thin LLM layer

Replaces the 4-stage/12-month narrative (target/stages/subjects_to_focus/
university_track) with profession_options, subjects_now, starter_actions and
university_requirements. growth_focus/skills_to_build are unchanged.

Revision ID: 0034
Revises: 0033
Create Date: 2026-07-22 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("direction_roadmaps", "target")
    op.drop_column("direction_roadmaps", "stages")
    op.drop_column("direction_roadmaps", "subjects_to_focus")
    op.drop_column("direction_roadmaps", "university_track")

    op.add_column(
        "direction_roadmaps",
        sa.Column(
            "profession_options", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )
    op.add_column(
        "direction_roadmaps",
        sa.Column(
            "subjects_now", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )
    op.add_column(
        "direction_roadmaps",
        sa.Column(
            "starter_actions", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )
    op.add_column(
        "direction_roadmaps",
        sa.Column(
            "university_requirements", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )


def downgrade() -> None:
    op.drop_column("direction_roadmaps", "university_requirements")
    op.drop_column("direction_roadmaps", "starter_actions")
    op.drop_column("direction_roadmaps", "subjects_now")
    op.drop_column("direction_roadmaps", "profession_options")

    op.add_column(
        "direction_roadmaps",
        sa.Column("target", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "direction_roadmaps",
        sa.Column("stages", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "direction_roadmaps",
        sa.Column("subjects_to_focus", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "direction_roadmaps",
        sa.Column("university_track", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
