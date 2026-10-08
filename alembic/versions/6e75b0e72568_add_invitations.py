"""add_invitations

Staff email invitations (PRO-459). `user_role_enum` and `locale_enum` already
exist (owned by earlier migrations), hence `create_type=False`.

Revision ID: 6e75b0e72568
Revises: 158b6fddafd6
Create Date: 2026-10-07 06:29:40.021003

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6e75b0e72568'
down_revision: Union[str, None] = '158b6fddafd6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('invitations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('role', postgresql.ENUM('student', 'admin', 'psychologist', name='user_role_enum', create_type=False), nullable=False),
    sa.Column('locale', postgresql.ENUM('ru', 'kk', name='locale_enum', create_type=False), server_default='ru', nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('invited_by', sa.UUID(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role <> 'student'", name='ck_invitations_staff_role'),
    sa.ForeignKeyConstraint(['invited_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index(op.f('ix_invitations_email'), 'invitations', ['email'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_invitations_email'), table_name='invitations')
    op.drop_table('invitations')
