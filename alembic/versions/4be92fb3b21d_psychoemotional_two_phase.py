"""psychoemotional_runs: split submission into start/finish (PRO-3xx)

Product change: the first color pick (`list1`) now happens before the main
test battery, the second (`list2`) at the very end — no longer one atomic
submit. `list2` / `list2_dt_ms` / `pause_actual_sec` are only known once the
run is finished, so they become nullable; a run with `list2 IS NULL` is an
in-progress (or abandoned) start that the scoring engine must ignore.

Revision ID: 4be92fb3b21d
Revises: f4b8e2a5c7d1
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4be92fb3b21d"
down_revision: Union[str, None] = "f4b8e2a5c7d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("psychoemotional_runs", "list2", nullable=True)
    op.alter_column("psychoemotional_runs", "list2_dt_ms", nullable=True)
    op.alter_column("psychoemotional_runs", "pause_actual_sec", nullable=True)


def downgrade() -> None:
    op.alter_column("psychoemotional_runs", "pause_actual_sec", nullable=False)
    op.alter_column("psychoemotional_runs", "list2_dt_ms", nullable=False)
    op.alter_column("psychoemotional_runs", "list2", nullable=False)
