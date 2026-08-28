"""merge_google_oauth_and_university_images_heads

Revision ID: fa81fa8a82f9
Revises: b3e7a1c9d4f2, bf4109ec3b43
Create Date: 2026-08-28 10:21:40.641269

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa81fa8a82f9'
down_revision: Union[str, None] = ('b3e7a1c9d4f2', 'bf4109ec3b43')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
