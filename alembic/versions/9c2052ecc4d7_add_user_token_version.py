"""Add a session version used to revoke access tokens after password reset.

Revision ID: 9c2052ecc4d7
Revises: 6a7b8c9d0e1f
Create Date: 2026-10-05 10:26:52.657057

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "9c2052ecc4d7"
down_revision: str | None = "6a7b8c9d0e1f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
