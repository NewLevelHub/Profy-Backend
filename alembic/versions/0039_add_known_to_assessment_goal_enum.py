"""add known to assessment_goal_enum

Revision ID: 0039
Revises: 0038
Create Date: 2026-07-27 00:00:00.000001
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE cannot run inside a transaction block in PostgreSQL.
    op.execute("COMMIT")
    op.execute("ALTER TYPE assessment_goal_enum ADD VALUE IF NOT EXISTS 'known'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without recreating the type.
    pass
