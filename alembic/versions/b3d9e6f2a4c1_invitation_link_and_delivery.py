"""invitation_link_and_delivery

Staff invitations: the encrypted token, so the admin can copy the link of a
pending invitation later, and the delivery state of the invitation email
reported by the Resend webhook.

Open invitations created before this migration have no ciphertext — their
link can't be shown again; a resend issues a new one.

Revision ID: b3d9e6f2a4c1
Revises: 6e75b0e72568
Create Date: 2026-10-07 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b3d9e6f2a4c1'
down_revision: Union[str, None] = '6e75b0e72568'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('invitations', sa.Column('token_ciphertext', sa.Text(), nullable=True))
    op.add_column('invitations', sa.Column('email_message_id', sa.String(length=64), nullable=True))
    op.add_column('invitations', sa.Column('email_status', sa.String(length=16), nullable=True))
    op.add_column('invitations', sa.Column('email_status_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_invitations_email_message_id'), 'invitations', ['email_message_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_invitations_email_message_id'), table_name='invitations')
    op.drop_column('invitations', 'email_status_at')
    op.drop_column('invitations', 'email_status')
    op.drop_column('invitations', 'email_message_id')
    op.drop_column('invitations', 'token_ciphertext')
