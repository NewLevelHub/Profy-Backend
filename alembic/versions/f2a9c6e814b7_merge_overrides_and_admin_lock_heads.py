"""merge overrides and admin-lock/google-id heads

Revision ID: f2a9c6e814b7
Revises: b8ebb1a442d0, e7c4b2a91f03
Create Date: 2026-09-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a9c6e814b7'
down_revision: Union[str, None] = ('b8ebb1a442d0', 'e7c4b2a91f03')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
