"""crm roles and staff full_name

CRM roles from ТЗ CRM Profile v4.1 §2 (PRO-497) and a display name for
staff accounts — specialists are shown by name in the schedule and CRM.

Revision ID: c375e89983f8
Revises: ff9d84dcd1ba
Create Date: 2026-10-20 08:30:48.096952

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c375e89983f8'
down_revision: Union[str, None] = 'ff9d84dcd1ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_ROLES = ("owner", "sales_head", "sales_manager", "marketer")


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        for role in _NEW_ROLES:
            op.execute(f"ALTER TYPE user_role_enum ADD VALUE IF NOT EXISTS '{role}'")

    op.add_column('users', sa.Column('full_name', sa.String(length=255), nullable=True))
    op.add_column('invitations', sa.Column('full_name', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('invitations', 'full_name')
    op.drop_column('users', 'full_name')
    # PostgreSQL cannot drop enum values without recreating the type; the
    # extra `user_role_enum` values stay, unused, after a downgrade.
