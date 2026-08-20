"""add university short_name/aliases/location

Restores fields already present in university-data/*.py source records
(short_name, aliases, location) that seed_kz_universities.py previously
read the file but never wrote to the DB. No data migration needed here —
scripts/seed_kz_universities.py backfills these on its next run from the
same source files it already reads.

Revision ID: 516b3b3bdabe
Revises: 5f7925c25fbb
Create Date: 2026-08-18 10:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '516b3b3bdabe'
down_revision: Union[str, None] = '5f7925c25fbb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("universities", sa.Column("short_name", sa.String(100), nullable=True))
    op.add_column(
        "universities",
        sa.Column("aliases", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column("universities", sa.Column("location", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("universities", "location")
    op.drop_column("universities", "aliases")
    op.drop_column("universities", "short_name")
