"""specialist week reminders

One «set next week's schedule» email per specialist per week (PRO-560).

Revision ID: fa166a6136ec
Revises: d96ecfc9ae72
Create Date: 2026-10-20 09:30:29.886379

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'fa166a6136ec'
down_revision: Union[str, None] = 'd96ecfc9ae72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('specialist_week_reminders',
    sa.Column('specialist_id', sa.UUID(), nullable=False),
    sa.Column('week_start', sa.Date(), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['specialist_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('specialist_id', 'week_start')
    )


def downgrade() -> None:
    op.drop_table('specialist_week_reminders')
