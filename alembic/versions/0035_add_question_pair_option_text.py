"""question_pairs.option_a_text/option_b_text (situational dilemma rewrite)

Middle pairs were built by zipping two independent Likert statements from
"opposite" RIASEC types / Big Five domains — statistically opposite on
average, but not mutually exclusive in the moment, so the forced choice
didn't read as a real dilemma (user feedback: "two unrelated questions").
These two nullable columns let a pair override what's shown per option with
a scenario-specific action, independent of the linked Question's own
Likert-statement text — scoring still keys off question_a_id/question_b_id,
untouched. Null (junior's pairs) keeps today's behavior: fall back to
question.short_text/text.

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-06 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("question_pairs", sa.Column("option_a_text", sa.String(), nullable=True))
    op.add_column("question_pairs", sa.Column("option_b_text", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("question_pairs", "option_b_text")
    op.drop_column("question_pairs", "option_a_text")
