"""add wellbeing to question_block_enum

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-02 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE cannot run inside a transaction block in PostgreSQL.
    op.execute("COMMIT")
    op.execute("ALTER TYPE question_block_enum ADD VALUE IF NOT EXISTS 'wellbeing'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without recreating the type.
    # Removing 'wellbeing' requires a full enum recreation; omitted intentionally.
    pass
