"""motivation_statements.text_junior (age-appropriate wording for 6-9)

The 36 motivation phrases were written around adult career life ("stable
job", "earn a lot of money", "become a known expert") — abstractions a 6-9
year old has no personal experience of. Format (3-way forced-choice) is
already fine for junior (not Likert), so this is a wording-only fix: an
optional second text per statement, shown instead of `text` only when the
requesting profile is junior (app/routers/motivation.py). Null is safe —
falls back to showing `text` to everyone, same as before this migration.

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-06 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "motivation_statements", sa.Column("text_junior", sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("motivation_statements", "text_junior")
