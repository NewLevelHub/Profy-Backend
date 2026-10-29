"""crm whatsapp messages

The WhatsApp chat with clients (`crm_messages`, app/services/whatsapp/) and the
«повторное обращение» mark of a deal. Empty until Green API is configured.

Revision ID: a18a2a2a67c1
Revises: cadb509a9d1c
Create Date: 2026-10-29 07:25:40.972692

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a18a2a2a67c1'
down_revision: Union[str, None] = 'cadb509a9d1c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('crm_messages',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('parent_id', sa.UUID(), nullable=True),
    sa.Column('deal_id', sa.UUID(), nullable=True),
    sa.Column('phone', sa.String(length=32), nullable=False),
    sa.Column('direction', sa.Enum('incoming', 'outgoing', name='messagedirection', native_enum=False), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('kind', sa.String(length=32), server_default='text', nullable=False),
    sa.Column('provider_id', sa.String(length=128), nullable=True),
    sa.Column('status', sa.Enum('received', 'pending', 'sent', 'delivered', 'read', 'failed', name='messagestatus', native_enum=False, length=16), nullable=False),
    sa.Column('author_id', sa.UUID(), nullable=True),
    sa.Column('ad', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deal_id'], ['crm_deals.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['parent_id'], ['crm_parents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider_id')
    )
    op.create_index(op.f('ix_crm_messages_at'), 'crm_messages', ['at'], unique=False)
    op.create_index(op.f('ix_crm_messages_deal_id'), 'crm_messages', ['deal_id'], unique=False)
    op.create_index(op.f('ix_crm_messages_parent_id'), 'crm_messages', ['parent_id'], unique=False)
    op.create_index(op.f('ix_crm_messages_phone'), 'crm_messages', ['phone'], unique=False)
    op.add_column('crm_deals', sa.Column('repeat', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('crm_deals', 'repeat')
    op.drop_index(op.f('ix_crm_messages_phone'), table_name='crm_messages')
    op.drop_index(op.f('ix_crm_messages_parent_id'), table_name='crm_messages')
    op.drop_index(op.f('ix_crm_messages_deal_id'), table_name='crm_messages')
    op.drop_index(op.f('ix_crm_messages_at'), table_name='crm_messages')
    op.drop_table('crm_messages')
