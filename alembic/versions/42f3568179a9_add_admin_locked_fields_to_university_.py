"""add_admin_locked_fields_to_university_and_program

Revision ID: 42f3568179a9
Revises: caf6ae824d45
Create Date: 2026-08-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '42f3568179a9'
down_revision: Union[str, None] = 'caf6ae824d45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "universities",
        sa.Column("admin_locked_fields", JSONB, nullable=False, server_default="[]"),
    )
    op.add_column(
        "programs",
        sa.Column("admin_locked_fields", JSONB, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("programs", "admin_locked_fields")
    op.drop_column("universities", "admin_locked_fields")
