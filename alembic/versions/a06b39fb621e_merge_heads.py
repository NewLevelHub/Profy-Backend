"""merge heads

Revision ID: a06b39fb621e
Revises: 60ed7d434ac8, a27baccf4197
Create Date: 2026-08-20 06:09:29.584167

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a06b39fb621e'
down_revision: Union[str, None] = ('60ed7d434ac8', 'a27baccf4197')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
