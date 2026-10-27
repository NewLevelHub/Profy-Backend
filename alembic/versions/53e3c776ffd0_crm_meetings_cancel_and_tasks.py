"""crm meetings cancel and tasks

Revision ID: 53e3c776ffd0
Revises: c7ce76ab052e
Create Date: 2026-10-21 07:53:55.832280

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '53e3c776ffd0'
down_revision: Union[str, None] = 'c7ce76ab052e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('crm_tasks',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('deal_id', sa.UUID(), nullable=True),
    sa.Column('assignee_id', sa.UUID(), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('type', sa.Enum('call', 'message', 'meeting', 'payment_check', 'reschedule', 'other', name='tasktype', native_enum=False, length=32), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('done_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('result', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deal_id'], ['crm_deals.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_crm_tasks_assignee_id'), 'crm_tasks', ['assignee_id'], unique=False)
    op.create_index(op.f('ix_crm_tasks_deal_id'), 'crm_tasks', ['deal_id'], unique=False)
    op.create_index(op.f('ix_crm_tasks_due_at'), 'crm_tasks', ['due_at'], unique=False)
    op.add_column('meetings', sa.Column('cancel_reason', sa.Text(), nullable=True))
    op.add_column('meetings', sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('meetings', sa.Column('rescheduled_from_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'meetings_rescheduled_from_id_fkey', 'meetings', 'meetings', ['rescheduled_from_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('meetings_rescheduled_from_id_fkey', 'meetings', type_='foreignkey')
    op.drop_column('meetings', 'rescheduled_from_id')
    op.drop_column('meetings', 'cancelled_at')
    op.drop_column('meetings', 'cancel_reason')
    op.drop_index(op.f('ix_crm_tasks_due_at'), table_name='crm_tasks')
    op.drop_index(op.f('ix_crm_tasks_deal_id'), table_name='crm_tasks')
    op.drop_index(op.f('ix_crm_tasks_assignee_id'), table_name='crm_tasks')
    op.drop_table('crm_tasks')
