"""merge pro-338 (psych_ai_analysis) and pro-337 (review gate) heads

Revision ID: c1d2e3f4a5b6
Revises: b3c4d5e6f7a8, b7e2d4a91c3f
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = ('b3c4d5e6f7a8', 'b7e2d4a91c3f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
