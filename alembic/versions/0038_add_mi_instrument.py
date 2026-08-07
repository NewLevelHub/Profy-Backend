"""add MI (Multiple-Intelligences-style) as a third question instrument, replacing RIASEC for junior

`questions` gains `mi_category` (new `mi_type_enum`, 8 values) and the
`question_instrument_enum` gains an `"mi"` value. Junior (6-9) stops
answering RIASEC content — TZ_Profi.md §4.1 excludes career orientation for
this age group — and answers MI pairs instead; Big Five stays for junior
unchanged. No existing data touched; old junior-tagged `riasec` rows are
left in place (excluded from junior queries in application code) rather than
migrated/deleted here.

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-07 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MI_TYPE_ENUM = postgresql.ENUM(
    "verbal", "logical", "musical", "visual", "bodily",
    "interpersonal", "intrapersonal", "naturalistic",
    name="mi_type_enum",
)


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block in PostgreSQL.
    op.execute("COMMIT")
    op.execute("ALTER TYPE question_instrument_enum ADD VALUE IF NOT EXISTS 'mi'")

    MI_TYPE_ENUM.create(op.get_bind())
    op.add_column("questions", sa.Column("mi_category", MI_TYPE_ENUM, nullable=True))


def downgrade() -> None:
    op.drop_column("questions", "mi_category")
    MI_TYPE_ENUM.drop(op.get_bind())
    # PostgreSQL does not support removing enum values without recreating the type.
