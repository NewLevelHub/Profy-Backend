"""add product feedback table

Revision ID: 2087d1e33179
Revises: 737ff08c158c
Create Date: 2026-08-19 07:59:09.296007

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2087d1e33179'
down_revision: Union[str, None] = '737ff08c158c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('product_feedback',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('assessment_id', sa.UUID(), nullable=True),
    sa.Column('relevance_score', sa.Integer(), nullable=False),
    sa.Column('helpful_sections', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['assessment_id'], ['assessments.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_product_feedback_assessment_id'), 'product_feedback', ['assessment_id'], unique=False)
    op.create_index(op.f('ix_product_feedback_user_id'), 'product_feedback', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_product_feedback_user_id'), table_name='product_feedback')
    op.drop_index(op.f('ix_product_feedback_assessment_id'), table_name='product_feedback')
    op.drop_table('product_feedback')
