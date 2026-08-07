"""add chosen_side to motivation_pair_responses (same-category polar pairs)

Motivation pairs are being redesigned from cross-category ipsative
comparisons ("Одни ребята любят X, другим важнее Y" with X != Y) to genuine
Harter-style same-category polar pairs (X vs low-X). Once `category_a ==
category_b` on every pair, `chosen_category` alone can no longer tell which
pole was picked, so scoring needs a new `chosen_side` column.

Backfills existing rows from the (still old, cross-category) `motivation_pairs`
content BEFORE that table gets reseeded — this migration must run before
scripts/seed_motivation_pairs.py is re-run with the new content, otherwise
the backfill has nothing correct to compare against.

Revision ID: 0039
Revises: 0038
Create Date: 2026-08-07 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAIR_SIDE_ENUM = postgresql.ENUM("a", "b", name="motivation_pair_side_enum")


def upgrade() -> None:
    PAIR_SIDE_ENUM.create(op.get_bind())
    op.add_column(
        "motivation_pair_responses",
        sa.Column("chosen_side", PAIR_SIDE_ENUM, nullable=True),
    )

    # Backfill from the pre-redesign motivation_pairs content: a response's
    # chosen_side is 'a' if chosen_category matches that pair's (old)
    # category_a, else 'b'.
    op.execute(
        """
        UPDATE motivation_pair_responses r
        SET chosen_side = (CASE WHEN r.chosen_category = p.category_a THEN 'a' ELSE 'b' END)::motivation_pair_side_enum
        FROM motivation_pairs p
        WHERE p.pair_index = r.pair_index
        """
    )

    op.alter_column("motivation_pair_responses", "chosen_side", nullable=False)


def downgrade() -> None:
    op.drop_column("motivation_pair_responses", "chosen_side")
    PAIR_SIDE_ENUM.drop(op.get_bind())
