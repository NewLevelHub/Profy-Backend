"""Enforce one pending psychoemotional run per assessment (PROFY-006).

Revision ID: 6a7b8c9d0e1f
Revises: 4f8c1d2e3a90
Create Date: 2026-10-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "6a7b8c9d0e1f"
down_revision: str | None = "4f8c1d2e3a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Incomplete rows are recovery state, not history. Keep the newest orphan
    # created by the old non-idempotent endpoint and remove older duplicates.
    op.execute(
        """
        DELETE FROM psychoemotional_runs
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY assessment_id
                        ORDER BY created_at DESC, id DESC
                    ) AS position
                FROM psychoemotional_runs
                WHERE list2 IS NULL
            ) ranked
            WHERE position > 1
        )
        """
    )
    op.create_index(
        "uq_psychoemotional_runs_assessment_pending",
        "psychoemotional_runs",
        ["assessment_id"],
        unique=True,
        postgresql_where=sa.text("list2 IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_psychoemotional_runs_assessment_pending",
        table_name="psychoemotional_runs",
    )
