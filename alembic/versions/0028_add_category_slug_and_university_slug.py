"""add category_slug to directions, slug to universities

Bridges the two independent slug vocabularies used for career matching
(Direction.slug, e.g. "mechanical-engineer") and program tagging
(Program.direction_slug, a curated ~10-category taxonomy). Direction rows
now carry category_slug so report_service can expose which of the 10
program categories a matched profession belongs to. University.slug lets
scripts/seed_kz_universities.py upsert idempotently against the real KZ
university-data/*.py datasets without duplicating rows already seeded by
scripts/seed_universities.py.

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-06 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "directions",
        sa.Column("category_slug", sa.String(length=50), nullable=False, server_default=""),
    )
    op.add_column(
        "universities",
        sa.Column("slug", sa.String(length=255), nullable=True),
    )
    op.create_unique_constraint("uq_universities_slug", "universities", ["slug"])
    op.create_index("ix_universities_slug", "universities", ["slug"])


def downgrade() -> None:
    op.drop_index("ix_universities_slug", table_name="universities")
    op.drop_constraint("uq_universities_slug", "universities", type_="unique")
    op.drop_column("universities", "slug")
    op.drop_column("directions", "category_slug")
