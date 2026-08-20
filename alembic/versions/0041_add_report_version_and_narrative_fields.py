"""analysis_results: report_version, strength_cards, thinking_style_notes

Storage groundwork for the student /result v2 redesign (TZ_Profi.md
§16-18, docs/rs-progress-notes.md) — this migration only adds the columns;
the LLM narrative pipeline that actually populates strength_cards/
thinking_style_notes with report_version=2 is separate, later work.

- `strength_cards` / `thinking_style_notes`: typed JSONB, NOT NULL DEFAULT
  '[]' — every existing row gets a valid empty list with no backfill step.
- `report_version` INTEGER NOT NULL DEFAULT 1 — every row existing before
  this migration (and every row inserted by code that hasn't been updated
  to write v2 narrative yet) is explicitly `1`. This is a stored fact, not
  something inferred at read time from whether strength_cards happens to be
  empty — a legacy row and a v2 row must be told apart by this column alone.

Revision ID: 0041
Revises: 0040
Create Date: 2026-08-11 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_results",
        sa.Column(
            "strength_cards",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "analysis_results",
        sa.Column(
            "thinking_style_notes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "analysis_results",
        sa.Column(
            "report_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )


def downgrade() -> None:
    op.drop_column("analysis_results", "report_version")
    op.drop_column("analysis_results", "thinking_style_notes")
    op.drop_column("analysis_results", "strength_cards")
