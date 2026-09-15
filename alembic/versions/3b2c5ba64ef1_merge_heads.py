"""merge heads

Revision ID: 3b2c5ba64ef1
Revises: 7db53544fd3d, e366cb88e71f
Create Date: 2026-09-11 08:26:43.643044

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b2c5ba64ef1'
down_revision: Union[str, None] = ('7db53544fd3d', 'e366cb88e71f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
