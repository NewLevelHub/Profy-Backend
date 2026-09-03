"""merge admin-lock and drop-google-id-index heads

Revision ID: e7c4b2a91f03
Revises: 42f3568179a9, d896a3811d5b
Create Date: 2026-09-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7c4b2a91f03'
down_revision: Union[str, None] = ('42f3568179a9', 'd896a3811d5b')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
