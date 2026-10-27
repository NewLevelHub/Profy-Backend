"""crm deals leave the review_scheduled stage

«Разбор назначен» is no longer a stage (the second call can be set before or
after the test; the deal card shows it), and the report now follows the
review: … → review_done → report_published. A deal on review_scheduled or
review_done already had its report published, so it is report_published
now. Data only; the column is a plain string.

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
    op.execute("UPDATE crm_deals SET stage = 'report_published' WHERE stage IN ('review_scheduled', 'review_done')")


def downgrade() -> None:
    # Nothing to restore: report_published is a stage of the old funnel too.
    pass
