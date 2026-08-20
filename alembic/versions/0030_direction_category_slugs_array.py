"""directions.category_slug (str) -> category_slugs (JSONB list)

Some professions genuinely span more than one of the ~10 program categories
(e.g. "Архитектор" matches real Kazakhstani "Архитектура" specialties, which
are tagged engineering-science, but is also an Artistic-type profession
whose closest peers sit in design-digital-art) — a single category_slug
forced report_service to pick just one, which meant "Найти университеты"
either showed the right engineering programs or the right design programs,
never both. category_slugs (JSONB array) lets a profession list every
category its real-world programs are tagged under.

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-06 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "directions",
        sa.Column("category_slugs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.execute(
        """
        UPDATE directions
        SET category_slugs = jsonb_build_array(category_slug)
        WHERE category_slug IS NOT NULL AND category_slug != ''
        """
    )
    op.drop_column("directions", "category_slug")


def downgrade() -> None:
    op.add_column(
        "directions",
        sa.Column("category_slug", sa.String(length=50), nullable=False, server_default=""),
    )
    op.execute(
        """
        UPDATE directions
        SET category_slug = COALESCE(category_slugs->>0, '')
        """
    )
    op.drop_column("directions", "category_slugs")
