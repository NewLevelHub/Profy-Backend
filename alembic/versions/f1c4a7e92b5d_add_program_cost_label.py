"""add_program_cost_label

Revision ID: f1c4a7e92b5d
Revises: a3b9c614590e
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1c4a7e92b5d'
down_revision: Union[str, None] = 'a3b9c614590e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("programs", sa.Column("cost_label", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("programs", "cost_label")
