"""analysis_results: final_analysis

Storage for the "Итог" (final analysis) narrative field — the 3-5 sentence
synthesis added to ReportNarrativeOutput that ties every earlier section
together. Follows the exact pattern of 0041's strength_cards/
thinking_style_notes: a plain NOT NULL DEFAULT '' column, no backfill step,
existing rows simply read back as an empty string until regenerated.

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-13 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_results",
        sa.Column(
            "final_analysis",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )


def downgrade() -> None:
    op.drop_column("analysis_results", "final_analysis")
