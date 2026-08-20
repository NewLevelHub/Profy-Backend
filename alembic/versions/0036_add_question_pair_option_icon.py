"""question_pairs.option_a_icon/option_b_icon (junior dilemma rewrite)

Same fix as 0035 (option_a_text/option_b_text) applied to icons: junior's
pairs are getting rewritten as genuine situational dilemmas too (the old
mechanical zip of two independent Likert items read as "two unrelated
questions" for middle, and junior has the identical issue). Once an
option's text becomes a scenario-specific action, the linked Question's
fixed icon may no longer fit, so it needs its own override — same
null-falls-back-to-question.icon behavior as text.

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-06 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("question_pairs", sa.Column("option_a_icon", sa.String(), nullable=True))
    op.add_column("question_pairs", sa.Column("option_b_icon", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("question_pairs", "option_b_icon")
    op.drop_column("question_pairs", "option_a_icon")
