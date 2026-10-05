"""add_top_career_why_to_analysis_results

Revision ID: 55c79b2331ee
Revises: 895570ac1160
Create Date: 2026-10-02 08:12:34.778833

«Почему тебе подходит» of the best match — the psychologist-view AI
analysis's reasoning: {"slug": ..., "text": ...} per locale row.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '55c79b2331ee'
down_revision: Union[str, None] = '895570ac1160'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('analysis_results', sa.Column('top_career_why', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('analysis_results', 'top_career_why')
