"""add_roadmap_recommended_paths

Revision ID: a3b9c614590e
Revises: 58c0026e6f31
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a3b9c614590e'
down_revision: Union[str, None] = '58c0026e6f31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'roadmaps',
        sa.Column('recommended_paths', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    op.drop_column('roadmaps', 'recommended_paths')
