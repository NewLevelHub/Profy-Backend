"""questions.short_text/icon + question_pairs table (junior forced-choice format)

TZ_Profi.md §13 bans Likert for the junior (6-9) branch — only icon-based
choice/image/scenario formats are allowed. `question_pairs` lets junior pick
between two existing junior-tier `questions` rows (referenced by FK, no text
duplication); `short_text`/`icon` give each of those rows a short button label
and an emoji icon for that picker UI. No new response table — a pair pick is
written as two ordinary `user_responses` rows (see question_pair_service.py),
so riasec_service/bigfive_service need no changes.

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-06 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

QUESTION_INSTRUMENT_ENUM = postgresql.ENUM(
    "riasec", "big_five", name="question_instrument_enum", create_type=False
)


def upgrade() -> None:
    op.add_column("questions", sa.Column("short_text", sa.String(), nullable=True))
    op.add_column("questions", sa.Column("icon", sa.String(), nullable=True))

    op.create_table(
        "question_pairs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instrument", QUESTION_INSTRUMENT_ENUM, nullable=False),
        sa.Column("pair_index", sa.Integer(), nullable=False),
        sa.Column(
            "question_a_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_b_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("frame", sa.String(), nullable=True),
    )
    op.create_index("ix_question_pairs_instrument", "question_pairs", ["instrument"])
    op.create_index("ix_question_pairs_pair_index", "question_pairs", ["pair_index"])


def downgrade() -> None:
    op.drop_index("ix_question_pairs_pair_index", table_name="question_pairs")
    op.drop_index("ix_question_pairs_instrument", table_name="question_pairs")
    op.drop_table("question_pairs")
    op.drop_column("questions", "icon")
    op.drop_column("questions", "short_text")
