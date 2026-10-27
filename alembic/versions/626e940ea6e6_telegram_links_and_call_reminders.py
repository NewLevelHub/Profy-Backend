"""telegram links and call reminders

The specialist's linked Telegram chat, the one-time link codes and the call
reminders that went out (app/models/telegram.py). Empty until the bot is
configured.

Revision ID: 626e940ea6e6
Revises: 1469e5b6dfbb
Create Date: 2026-10-27 06:51:16.665931

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '626e940ea6e6'
down_revision: Union[str, None] = '1469e5b6dfbb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('telegram_link_codes',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id'),
    sa.UniqueConstraint('code_hash')
    )
    op.create_table('telegram_links',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('chat_id', sa.BigInteger(), nullable=False),
    sa.Column('linked_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id'),
    sa.UniqueConstraint('chat_id')
    )
    op.create_table('telegram_meeting_reminders',
    sa.Column('meeting_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('meeting_id', 'kind')
    )


def downgrade() -> None:
    op.drop_table('telegram_meeting_reminders')
    op.drop_table('telegram_links')
    op.drop_table('telegram_link_codes')
