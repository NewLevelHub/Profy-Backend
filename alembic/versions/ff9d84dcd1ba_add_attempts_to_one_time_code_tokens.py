"""add attempts to one-time code tokens

A six-digit emailed code (email verification, password reset) now counts the
wrong guesses made at it and is burned at the limit — see
``app/services/token_utils.py``. Existing rows start at zero; codes issued
before this deploy stop matching anyway (their hash became keyed) and expire
within 15 minutes.

Revision ID: ff9d84dcd1ba
Revises: 3f451feb9e05
Create Date: 2026-10-12 06:21:11.712308

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ff9d84dcd1ba'
down_revision: Union[str, None] = '3f451feb9e05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'email_verification_tokens',
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    )
    op.add_column(
        'password_reset_tokens',
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('password_reset_tokens', 'attempts')
    op.drop_column('email_verification_tokens', 'attempts')
