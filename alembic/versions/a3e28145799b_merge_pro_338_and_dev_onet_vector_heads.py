"""merge pro_338 and dev onet vector heads

Revision ID: a3e28145799b
Revises: c1d2e3f4a5b6, c8a3f1e92b4d
Create Date: 2026-09-18 11:01:57.540387

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3e28145799b'
down_revision: Union[str, None] = ('c1d2e3f4a5b6', 'c8a3f1e92b4d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
