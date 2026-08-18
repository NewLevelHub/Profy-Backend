"""add_updated_at_source_url

Revision ID: d7c227f4c0b2
Revises: a3f9c1d84e02
Create Date: 2026-08-17 09:41:27.057511

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7c227f4c0b2'
down_revision: Union[str, None] = 'a3f9c1d84e02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("universities", "programs"):
        op.add_column(table, sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column("source_url", sa.Text(), nullable=True))


def downgrade() -> None:
    for table in ("universities", "programs"):
        op.drop_column(table, "source_url")
        op.drop_column(table, "updated_at")
