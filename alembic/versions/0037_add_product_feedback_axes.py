"""add per-axis ratings to product_feedback

Revision ID: 0037
Revises: 0036
Create Date: 2026-07-24 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Reuses the enum type created in 0036 — must not attempt to CREATE TYPE again.
feedback_rating_enum = postgresql.ENUM(
    "good", "neutral", "bad", name="product_feedback_rating_enum", create_type=False
)

AXIS_COLUMNS = ["questions_rating", "result_match_rating", "plan_usefulness_rating", "design_rating"]


def upgrade() -> None:
    op.alter_column("product_feedback", "rating", new_column_name="overall_rating")
    for column_name in AXIS_COLUMNS:
        op.add_column(
            "product_feedback",
            sa.Column(column_name, feedback_rating_enum, nullable=True),
        )


def downgrade() -> None:
    for column_name in AXIS_COLUMNS:
        op.drop_column("product_feedback", column_name)
    op.alter_column("product_feedback", "overall_rating", new_column_name="rating")
