"""crm tariff psychologist review

Revision ID: 7a7430acb874
Revises: 93f9359dab74
Create Date: 2026-10-22 10:01:53.429854

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7a7430acb874'
down_revision: Union[str, None] = '93f9359dab74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Every existing tariff keeps the review it has had so far; the owner
    # unticks it in the CRM where the report may go to the student at once.
    op.add_column('crm_tariffs', sa.Column('psychologist_review', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('crm_deals', sa.Column('psychologist_review', sa.Boolean(), nullable=True))
    # Deals that already have a tariff were sold with a review.
    op.execute("UPDATE crm_deals SET psychologist_review = true WHERE tariff_code IS NOT NULL")


def downgrade() -> None:
    op.drop_column('crm_deals', 'psychologist_review')
    op.drop_column('crm_tariffs', 'psychologist_review')
