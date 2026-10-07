"""add_source_to_analysis_result_review_edits

Revision ID: 895570ac1160
Revises: 1db282a54f2f
Create Date: 2026-10-02 07:28:37.335651

Who made a review edit: the psychologist, or the system putting the AI
analysis's recommended profession at the top of the careers list. Existing
rows are all psychologist edits (the server default).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '895570ac1160'
down_revision: Union[str, None] = '1db282a54f2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SOURCE_ENUM = postgresql.ENUM(
    'psychologist', 'ai_recommendation', name='analysis_result_review_edit_source_enum'
)


def upgrade() -> None:
    _SOURCE_ENUM.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'analysis_result_review_edits',
        sa.Column(
            'source',
            postgresql.ENUM(name='analysis_result_review_edit_source_enum', create_type=False),
            server_default='psychologist',
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('analysis_result_review_edits', 'source')
    _SOURCE_ENUM.drop(op.get_bind(), checkfirst=True)
