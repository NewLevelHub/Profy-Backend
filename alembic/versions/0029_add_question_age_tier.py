"""add age_tier to questions (shorter test for junior/middle)

`questions.age_tier` marks the minimum age branch a question is shown to.
Reuses the existing `age_group_enum` Postgres type (already created by
`profiles.age_group`'s own migration) — not a duplicate type. Existing rows
default to 'senior' (safe: nothing is hidden until the banks are reseeded
with real per-question tiers via scripts/seed_riasec_questions.py and
scripts/seed_bigfive_questions.py).

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-06 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AGE_GROUP_ENUM = postgresql.ENUM(
    "junior", "middle", "senior", name="age_group_enum", create_type=False
)


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column("age_tier", AGE_GROUP_ENUM, nullable=False, server_default="senior"),
    )
    op.create_index("ix_questions_age_tier", "questions", ["age_tier"])


def downgrade() -> None:
    op.drop_index("ix_questions_age_tier", table_name="questions")
    op.drop_column("questions", "age_tier")
