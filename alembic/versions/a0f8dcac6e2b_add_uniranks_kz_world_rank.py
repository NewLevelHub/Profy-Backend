"""add_uniranks_kz_world_rank

Revision ID: a0f8dcac6e2b
Revises: 9fe0feff92b9
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a0f8dcac6e2b'
down_revision: Union[str, None] = '9fe0feff92b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("universities", sa.Column("uniranks_kz_rank", sa.Integer(), nullable=True))
    op.add_column("universities", sa.Column("uniranks_world_rank", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("universities", "uniranks_world_rank")
    op.drop_column("universities", "uniranks_kz_rank")
