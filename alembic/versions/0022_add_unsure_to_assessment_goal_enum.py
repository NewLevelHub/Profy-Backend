"""add unsure to assessment_goal_enum

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-09 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE cannot run inside a transaction block in PostgreSQL.
    op.execute("COMMIT")
    op.execute("ALTER TYPE assessment_goal_enum ADD VALUE IF NOT EXISTS 'unsure'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without recreating the type.
    pass
