"""crm student invites and account link

The one-time link that ties a student's Profile account to the deal, and
the link itself on `crm_deals` (ТЗ §4.4).

Revision ID: 9ea3b96a00af
Revises: f206e493c0c9
Create Date: 2026-10-22 06:56:44.021616

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9ea3b96a00af'
down_revision: Union[str, None] = 'f206e493c0c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('crm_student_invites',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('deal_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('token_ciphertext', sa.Text(), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('used_by', sa.UUID(), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deal_id'], ['crm_deals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['used_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index(op.f('ix_crm_student_invites_deal_id'), 'crm_student_invites', ['deal_id'], unique=False)
    op.add_column('crm_deals', sa.Column('student_user_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_crm_deals_student_user_id'), 'crm_deals', ['student_user_id'], unique=False)
    op.create_foreign_key(
        'crm_deals_student_user_id_fkey', 'crm_deals', 'users', ['student_user_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('crm_deals_student_user_id_fkey', 'crm_deals', type_='foreignkey')
    op.drop_index(op.f('ix_crm_deals_student_user_id'), table_name='crm_deals')
    op.drop_column('crm_deals', 'student_user_id')
    op.drop_index(op.f('ix_crm_student_invites_deal_id'), table_name='crm_student_invites')
    op.drop_table('crm_student_invites')
