"""merge kz localization epic into dev

Revision ID: c4e7f1a9d2b6
Revises: b2d6f0a3c1e8, f2a9c6e814b7
Create Date: 2026-09-04 07:41:01.625875

Empty merge node reconciling the two alembic heads that `pro-254` inherited
when `origin/dev` was merged in: the KZ localization epic's chain
(d80fbf5d1f43 -> f3b9c1d47a20 -> a1c5e9d2b7f4 -> b2d6f0a3c1e8) and dev's own
chain ending at the f2a9c6e814b7 merge node (admin-lock + question-bank
overrides + google_id index). No schema change — the two chains touch
disjoint tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e7f1a9d2b6'
down_revision: Union[str, None] = ('b2d6f0a3c1e8', 'f2a9c6e814b7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
