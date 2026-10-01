"""merge role/psychologist/favorites heads with question uniqueness constraint

Revision ID: ab5271e14fae
Revises: 3b2c5ba64ef1, 4d28ab54e64c
Create Date: 2026-09-15 06:30:41.589967

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab5271e14fae'
down_revision: Union[str, None] = ('3b2c5ba64ef1', '4d28ab54e64c')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
