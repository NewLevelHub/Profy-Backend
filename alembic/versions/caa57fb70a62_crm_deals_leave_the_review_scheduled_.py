"""crm deals leave the review_scheduled stage

«Разбор назначен» is no longer a stage (the second call can be set before or
after the test; the deal card shows it). A deal there had its report
published, so it goes back to report_published. Data only; the column is a
plain string.

Revision ID: caa57fb70a62
Revises: 196621163b47
Create Date: 2026-10-27 06:15:52.111089

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'caa57fb70a62'
down_revision: Union[str, None] = '196621163b47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE crm_deals SET stage = 'report_published' WHERE stage = 'review_scheduled'")


def downgrade() -> None:
    # Which of those deals had a set second call is still in `meetings`;
    # nothing to restore — the old code reads report_published as well.
    pass
