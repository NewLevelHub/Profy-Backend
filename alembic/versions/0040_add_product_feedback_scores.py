"""add raw 1-5 scores to product_feedback

Revision ID: 0040
Revises: 0039
Create Date: 2026-07-30 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The frontend previously collapsed its 1-5 picker into the good/neutral/bad
# enum before ever submitting — losing precision the admin analytics then
# had to approximate back (good=5/neutral=3/bad=1). These columns store the
# real value instead; the *_rating enum columns stay as the derived,
# always-present category (still used for filtering/badges in the admin
# list), now computed server-side in product_feedback_service.create_feedback
# rather than duplicated on the frontend. Nullable because rows submitted
# before this migration have no score to backfill.
SCORE_COLUMNS = [
    "overall_score",
    "questions_score",
    "result_match_score",
    "plan_usefulness_score",
    "design_score",
]


def upgrade() -> None:
    for column_name in SCORE_COLUMNS:
        op.add_column(
            "product_feedback",
            sa.Column(column_name, sa.SmallInteger(), nullable=True),
        )
        op.create_check_constraint(
            f"ck_product_feedback_{column_name}_range",
            "product_feedback",
            f"{column_name} IS NULL OR {column_name} BETWEEN 1 AND 5",
        )


def downgrade() -> None:
    for column_name in SCORE_COLUMNS:
        op.drop_constraint(f"ck_product_feedback_{column_name}_range", "product_feedback", type_="check")
        op.drop_column("product_feedback", column_name)
