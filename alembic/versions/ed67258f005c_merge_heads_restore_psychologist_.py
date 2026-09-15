"""merge heads (restore psychologist assignments)

Revision ID: ed67258f005c
Revises: 3b2c5ba64ef1, 4be92fb3b21d, e4ed44aa0d52
Create Date: 2026-09-14 06:05:13.679046

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ed67258f005c'
down_revision: Union[str, None] = ('3b2c5ba64ef1', '4be92fb3b21d', 'e4ed44aa0d52')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
