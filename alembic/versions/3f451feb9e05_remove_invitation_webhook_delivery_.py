"""remove invitation webhook delivery fields

Delivery tracking was intentionally retired before release. Keep the
synchronous ``email_status`` result, but remove the provider message id and
webhook timestamp so databases that already applied the branch migration
converge on the simplified schema.

Revision ID: 3f451feb9e05
Revises: b3d9e6f2a4c1
Create Date: 2026-10-07 10:49:49.186097

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f451feb9e05'
down_revision: Union[str, None] = 'b3d9e6f2a4c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f('ix_invitations_email_message_id'), table_name='invitations')
    op.drop_column('invitations', 'email_status_at')
    op.drop_column('invitations', 'email_message_id')


def downgrade() -> None:
    op.add_column(
        'invitations',
        sa.Column('email_message_id', sa.String(length=64), nullable=True),
    )
    op.add_column(
        'invitations',
        sa.Column('email_status_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f('ix_invitations_email_message_id'),
        'invitations',
        ['email_message_id'],
        unique=False,
    )
