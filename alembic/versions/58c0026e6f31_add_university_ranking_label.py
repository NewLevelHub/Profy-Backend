"""add_university_ranking_label

Revision ID: 58c0026e6f31
Revises: 516b3b3bdabe
Create Date: 2026-08-18 00:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '58c0026e6f31'
down_revision: Union[str, None] = '516b3b3bdabe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("universities", sa.Column("ranking_label", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("universities", "ranking_label")
