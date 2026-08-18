"""add_roadmap_additional_resources

Revision ID: c7e2a9f1d3b6
Revises: a3b9c614590e
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c7e2a9f1d3b6'
down_revision: Union[str, None] = 'f1c4a7e92b5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'roadmaps',
        sa.Column('additional_resources', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
    )
    op.add_column(
        'direction_roadmaps',
        sa.Column('additional_resources', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    op.drop_column('direction_roadmaps', 'additional_resources')
    op.drop_column('roadmaps', 'additional_resources')
