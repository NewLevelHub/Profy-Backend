"""Replace direction_slug (String) with direction_slugs (JSONB array)

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-22 00:00:00.000000

Why: a program can legitimately cover multiple akinator specialties
(e.g. a DevOps course maps to both "software-engineer" and
"it-infrastructure-security"). Storing a list in JSONB with a GIN index
allows the ?| (has-any-key equivalent for arrays) overlap operator to
find programs matching any of the user's allowed slugs in a single index
scan.
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
    # 1. Add the new nullable column so we can backfill it before making it NOT NULL.
    op.add_column(
        "programs",
        sa.Column("direction_slugs", postgresql.JSONB(), nullable=True),
    )

    # 2. Backfill: wrap the existing single slug into a one-element JSON array.
    op.execute(
        "UPDATE programs SET direction_slugs = jsonb_build_array(direction_slug)"
    )

    # 3. Now the column is fully populated — enforce NOT NULL.
    op.alter_column("programs", "direction_slugs", nullable=False)

    # 4. Drop the old index if it exists, then the old column.
    #    inspect() is not available in op context; use execute() to check
    #    pg_indexes directly — avoids any "index does not exist" error.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'programs'
                  AND indexname = 'ix_programs_direction_slug'
            ) THEN
                DROP INDEX ix_programs_direction_slug;
            END IF;
        END $$;
        """
    )
    op.drop_column("programs", "direction_slug")

    # 5. GIN index so ?| (array overlap) uses an index scan instead of a seqscan.
    op.create_index(
        "ix_programs_direction_slugs_gin",
        "programs",
        ["direction_slugs"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    # 1. Remove the GIN index.
    op.drop_index("ix_programs_direction_slugs_gin", table_name="programs")

    # 2. Re-add the old column (nullable first so we can backfill).
    op.add_column(
        "programs",
        sa.Column("direction_slug", sa.String(length=100), nullable=True),
    )

    # 3. Backfill: take the first element of the JSON array as the single slug.
    op.execute("UPDATE programs SET direction_slug = direction_slugs->>0")

    # 4. Enforce NOT NULL now that every row has a value.
    op.alter_column("programs", "direction_slug", nullable=False)

    # 5. Drop the new column.
    op.drop_column("programs", "direction_slugs")

    # 6. Recreate the original btree index on direction_slug.
    op.create_index(
        "ix_programs_direction_slug",
        "programs",
        ["direction_slug"],
    )
