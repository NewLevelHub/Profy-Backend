"""add age_groups to directions

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-09 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects import postgresql
import sqlalchemy as sa

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing directions are all adult/professional → default them to senior-only.
    # The seed script re-runs to set proper age_groups and add kid-friendly families.
    op.add_column(
        "directions",
        sa.Column(
            "age_groups",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[\"senior\"]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("directions", "age_groups")
