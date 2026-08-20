"""merge heads

Revision ID: 60ed7d434ac8
Revises: 0043, 2087d1e33179, c7e2a9f1d3b6
Create Date: 2026-08-20 04:56:32.110929

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '60ed7d434ac8'
down_revision: Union[str, None] = ('0043', '2087d1e33179', 'c7e2a9f1d3b6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
