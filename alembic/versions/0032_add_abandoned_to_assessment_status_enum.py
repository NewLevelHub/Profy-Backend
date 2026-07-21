"""add abandoned to assessment_status_enum

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-20 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE cannot run inside a transaction block in PostgreSQL.
    op.execute("COMMIT")
    op.execute("ALTER TYPE assessment_status_enum ADD VALUE IF NOT EXISTS 'abandoned'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without recreating the type.
    pass
