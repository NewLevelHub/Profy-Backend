"""merge heads

Revision ID: e366cb88e71f
Revises: a1c5f39be702, d47e8c105b23
Create Date: 2026-09-11 07:54:02.818439

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e366cb88e71f'
down_revision: Union[str, None] = ('a1c5f39be702', 'd47e8c105b23')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
