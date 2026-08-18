"""program_directions m2m, drop programs.profession_slugs

Replaces `Program.profession_slugs` (a JSONB array of `Direction.slug`
strings, matched by containment — no FK, no referential integrity, a
renamed/deleted Direction silently orphans the match) with a real M2M
table backed by foreign keys. Data is backfilled from the existing JSONB
array by matching each slug against `directions.slug` before the column is
dropped, so no mapping is lost.

Revision ID: 5f7925c25fbb
Revises: 66993561592c
Create Date: 2026-08-18 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5f7925c25fbb'
down_revision: Union[str, None] = '66993561592c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "program_directions",
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("direction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["direction_id"], ["directions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("program_id", "direction_id"),
    )
    op.create_index(
        "ix_program_directions_direction_id", "program_directions", ["direction_id"]
    )

    op.execute(
        """
        INSERT INTO program_directions (program_id, direction_id)
        SELECT DISTINCT p.id, d.id
        FROM programs p
        CROSS JOIN LATERAL jsonb_array_elements_text(p.profession_slugs) AS slug(value)
        JOIN directions d ON d.slug = slug.value
        """
    )

    op.drop_index("ix_programs_profession_slugs", table_name="programs")
    op.drop_column("programs", "profession_slugs")


def downgrade() -> None:
    op.add_column(
        "programs",
        sa.Column("profession_slugs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.create_index(
        "ix_programs_profession_slugs", "programs", ["profession_slugs"], postgresql_using="gin"
    )

    op.execute(
        """
        UPDATE programs p
        SET profession_slugs = COALESCE(sub.slugs, '[]'::jsonb)
        FROM (
            SELECT pd.program_id, jsonb_agg(d.slug) AS slugs
            FROM program_directions pd
            JOIN directions d ON d.id = pd.direction_id
            GROUP BY pd.program_id
        ) sub
        WHERE p.id = sub.program_id
        """
    )

    op.drop_index("ix_program_directions_direction_id", table_name="program_directions")
    op.drop_table("program_directions")
