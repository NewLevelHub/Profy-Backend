"""astur_runs.locale

`app/models/astur_run.py`'s `AsturRun.locale` (plain `String`, not the
`locale_enum` type `users.locale`/`users.locale_explicit` use — PRO-338
Ф4.4 records which locale a run was taken in, same idea as `users.locale`
but never needed the enum's "explicit pick" bookkeeping) was declared on
the model with no migration ever adding the column — found via a full
model-vs-actual-schema audit (PRO-424) that turned up exactly this one gap
and nothing else across every table. `server_default` backfills existing
rows to the model's own Python-side default ("ru") rather than leaving
them NULL against a NOT NULL column.

Revision ID: b1c2d3e4f5a6
Revises: a4f7c2e9d3b1
Create Date: 2026-09-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'a4f7c2e9d3b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "astur_runs",
        sa.Column("locale", sa.String(), nullable=False, server_default="ru"),
    )


def downgrade() -> None:
    op.drop_column("astur_runs", "locale")
