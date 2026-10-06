"""Enforce one active assessment per profile (PROFY-004).

Revision ID: 4f8c1d2e3a90
Revises: 55c79b2331ee
Create Date: 2026-10-05 00:00:00.000000

The service-level check was a classic check-then-insert race. Clean up any
duplicates that may already exist by keeping the newest active attempt, then
make the invariant authoritative in PostgreSQL with a partial unique index.
Older duplicate attempts are abandoned state, so deleting them matches the
existing restart behavior and cascades their partial child data.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "4f8c1d2e3a90"
down_revision: str | None = "55c79b2331ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM assessments
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY profile_id
                        ORDER BY created_at DESC, id DESC
                    ) AS position
                FROM assessments
                WHERE status = 'in_progress'
            ) ranked
            WHERE position > 1
        )
        """
    )
    op.create_index(
        "uq_assessments_profile_single_active",
        "assessments",
        ["profile_id"],
        unique=True,
        postgresql_where=sa.text("status = 'in_progress'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_assessments_profile_single_active", table_name="assessments"
    )
