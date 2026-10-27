"""crm tariff call optional

Revision ID: 29c9e806ad2e
Revises: 7a7430acb874
Create Date: 2026-10-22 10:16:45.706768

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '29c9e806ad2e'
down_revision: Union[str, None] = '7a7430acb874'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A tariff without «Консультация и проверка отчёта психологом» has no call.
    op.alter_column('crm_tariffs', 'meeting_minutes', existing_type=sa.SmallInteger(), nullable=True)
    op.execute("UPDATE crm_tariffs SET meeting_minutes = NULL WHERE psychologist_review = false")


def downgrade() -> None:
    op.execute("UPDATE crm_tariffs SET meeting_minutes = 30 WHERE meeting_minutes IS NULL")
    op.alter_column('crm_tariffs', 'meeting_minutes', existing_type=sa.SmallInteger(), nullable=False)
