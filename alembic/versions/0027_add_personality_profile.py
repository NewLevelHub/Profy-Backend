"""add personality_profile / personality_notes for the "Твой характер" section

Full 5-trait Big Five profile (Neuroticism flipped to Emotional Stability
for display) plus one tiered note per trait — see
app/services/bigfive_content.py:build_personality_profile. Distinct from the
existing admin-only `big_five` column and the 3-item `personality_highlights`.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-06 00:00:00.000000
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
    op.add_column(
        "analysis_results",
        sa.Column("personality_profile", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "analysis_results",
        sa.Column("personality_notes", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("analysis_results", "personality_notes")
    op.drop_column("analysis_results", "personality_profile")
