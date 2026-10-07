"""analysis_results.psych_ai_analysis

Specialist-only AI analysis for the psychologist report: per-block ~2-
sentence commentary, a final synthesis, and one profession picked (never
invented) from the student's own already-computed top-10 `careers` list.
Generated lazily on first psychologist view of a report and cached here
(same "raw data now, computed field later" nullable-JSONB precedent as
`validity`/`psychoemotional` on this same table) — `NULL` until then, and
after an explicit regenerate.

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f7
Create Date: 2026-09-17 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "a1b2c3d4e5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_results",
        sa.Column("psych_ai_analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_results", "psych_ai_analysis")
