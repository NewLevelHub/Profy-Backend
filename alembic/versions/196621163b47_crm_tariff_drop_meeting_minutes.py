"""crm tariff drop meeting minutes

Revision ID: 196621163b47
Revises: 29c9e806ad2e
Create Date: 2026-10-23 07:58:50.017286

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '196621163b47'
down_revision: Union[str, None] = '29c9e806ad2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The CRM always books a 30-minute first call; the 60-minute second one
    # the specialist sets. The tariff no longer carries a call length.
    op.drop_column('crm_tariffs', 'meeting_minutes')


def downgrade() -> None:
    op.add_column('crm_tariffs', sa.Column('meeting_minutes', sa.SmallInteger(), nullable=True))
    op.execute("UPDATE crm_tariffs SET meeting_minutes = 30 WHERE psychologist_review")
