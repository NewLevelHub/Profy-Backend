"""add unique constraint on questions instrument+order

Revision ID: 4d28ab54e64c
Revises: f7c1e9b4a608
Create Date: 2026-09-15 06:04:28.818313

`order` is each instrument's natural key into its bank (riasec/big_five/mi
number their own banks independently starting at 1), so uniqueness must be
the pair, not `order` alone. Nothing enforced this at the DB level before —
the locale-row duplication just fixed in e5a9f2d6c341..f7c1e9b4a608 is the
concrete case of what silently drifting on this natural key looks like
(seed_*.py's upsert-by-order dict masks a second row instead of erroring).
This turns any future violation into a loud IntegrityError at write time.

Safe to add: no existing (instrument, order) duplicates as of this
migration (checked directly), and no test fixture creates two Question
rows sharing an (instrument, order) pair.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d28ab54e64c'
down_revision: Union[str, None] = 'f7c1e9b4a608'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_questions_instrument_order", "questions", ["instrument", "order"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_questions_instrument_order", "questions", type_="unique")
