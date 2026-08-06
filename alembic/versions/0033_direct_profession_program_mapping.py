"""programs.profession_slugs (direct mapping), drop direction_slug and directions.category_slugs

Replaces the category-bridge matching system entirely. That system inferred
"this program matches this profession" via a shared ~18-category label
(Program.direction_slug <-> Direction.category_slugs), classified by keyword
matching (scripts/specialty_category_lookup.py). It kept producing wrong
results because a shared category is not the same thing as a real match — a
"style" word like "инженерия" put an airline pilot and a food-production
technologist in the same bucket. scripts/specialty_profession_map.py now
hand-maps each real specialty directly to the profession(s) it actually
prepares someone for, stored straight on Program — no intermediate category
needed, nothing left to reconcile.

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-06 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "programs",
        sa.Column("profession_slugs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.create_index(
        "ix_programs_profession_slugs", "programs", ["profession_slugs"], postgresql_using="gin"
    )
    op.drop_column("programs", "direction_slug")
    op.drop_column("directions", "category_slugs")


def downgrade() -> None:
    op.add_column(
        "directions",
        sa.Column("category_slugs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "programs",
        sa.Column("direction_slug", sa.String(length=100), nullable=False, server_default=""),
    )
    op.drop_index("ix_programs_profession_slugs", table_name="programs")
    op.drop_column("programs", "profession_slugs")
