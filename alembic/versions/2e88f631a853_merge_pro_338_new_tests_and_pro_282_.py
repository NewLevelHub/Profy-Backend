"""merge pro-338 (new tests) and pro-282 (psych block) heads

Revision ID: 2e88f631a853
Revises: a1b2c3d4e5f6, ed67258f005c
Create Date: 2026-09-15 07:48:01.941577

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2e88f631a853'
down_revision: Union[str, None] = ('a1b2c3d4e5f6', 'ed67258f005c')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
