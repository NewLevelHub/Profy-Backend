"""add_uniranks_note

Revision ID: 66993561592c
Revises: a0f8dcac6e2b
Create Date: 2026-08-18 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '66993561592c'
down_revision: Union[str, None] = 'a0f8dcac6e2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("universities", sa.Column("uniranks_note", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("universities", "uniranks_note")
