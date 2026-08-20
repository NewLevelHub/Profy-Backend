"""question_pairs.age_tier (dilemma/scenario pairs now also for middle)

Previously question_pairs only ever held junior pairs (the whole junior test
is pairs). Now middle also gets a subset of its questions woven into pairs
into the ordinary Likert flow (see buildDisplaySequence.ts on the frontend),
so pairs need to say which single age group they belong to. Unlike
questions.age_tier (checked cumulatively via visible_tiers()), this is an
exact match — a junior pair is never shown to middle or vice versa.

server_default='junior' backfills the 34 existing rows correctly (they were
all junior pairs before this migration); no data loss.

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-06 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AGE_GROUP_ENUM = postgresql.ENUM(
    "junior", "middle", "senior", name="age_group_enum", create_type=False
)


def upgrade() -> None:
    op.add_column(
        "question_pairs",
        sa.Column("age_tier", AGE_GROUP_ENUM, nullable=False, server_default="junior"),
    )
    op.create_index("ix_question_pairs_age_tier", "question_pairs", ["age_tier"])


def downgrade() -> None:
    op.drop_index("ix_question_pairs_age_tier", table_name="question_pairs")
    op.drop_column("question_pairs", "age_tier")
