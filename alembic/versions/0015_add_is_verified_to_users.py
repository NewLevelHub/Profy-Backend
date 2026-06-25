"""add is_verified to users

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-25 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("users", "is_verified", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "is_verified")
