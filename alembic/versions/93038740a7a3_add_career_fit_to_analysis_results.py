"""add_career_fit_to_analysis_results

The careers' «Почему тебе подходит», locale-free per career slug
(app/services/career_fit_service.py). Nullable: reports built before it get
it from scripts/backfill_career_fit.py. Autogenerate also listed the
pre-existing drift from alembic/known_schema_drift.txt — left out.

Revision ID: 93038740a7a3
Revises: 75992b0ec5d3
Create Date: 2026-10-01 11:04:59.327268

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '93038740a7a3'
down_revision: Union[str, None] = '75992b0ec5d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('analysis_results', sa.Column('career_fit', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('analysis_results', 'career_fit')
