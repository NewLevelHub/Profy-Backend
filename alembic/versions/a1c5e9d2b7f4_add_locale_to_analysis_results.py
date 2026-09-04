"""add locale to analysis_results

Revision ID: a1c5e9d2b7f4
Revises: f3b9c1d47a20
Create Date: 2026-09-04 12:00:00.000000

KZ-405 — the report narrative is the only live AI artifact; it is persisted in
`analysis_results` (one row per assessment) and cached in Redis. To let a `ru`
and a `kk` report for the same assessment coexist (KZ-406 lazy regeneration on
language switch), `analysis_results` gets a `locale` column and the single-column
UNIQUE on `assessment_id` becomes a composite `(assessment_id, locale)` UNIQUE
plus a plain lookup index.

`locale_enum` already exists (migration d80fbf5d1f43); reused, never re-created.
Existing rows are Russian and take `locale='ru'` from the column default.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1c5e9d2b7f4"
down_revision: Union[str, None] = "f3b9c1d47a20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "analysis_results"
_LOOKUP_INDEX = "ix_analysis_results_assessment_id"
_UQ = "uq_analysis_results_assessment_id_locale"


def _locale_type() -> postgresql.ENUM:
    return postgresql.ENUM("ru", "kk", name="locale_enum", create_type=False)


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column("locale", _locale_type(), nullable=False, server_default="ru"),
    )
    # demote the UNIQUE index on assessment_id to a plain lookup index
    op.drop_index(_LOOKUP_INDEX, table_name=_TABLE)
    op.create_index(_LOOKUP_INDEX, _TABLE, ["assessment_id"])
    op.create_unique_constraint(_UQ, _TABLE, ["assessment_id", "locale"])


def downgrade() -> None:
    op.drop_constraint(_UQ, _TABLE, type_="unique")
    op.drop_index(_LOOKUP_INDEX, table_name=_TABLE)
    # a downgrade only makes sense if no assessment has more than one locale row
    op.create_index(_LOOKUP_INDEX, _TABLE, ["assessment_id"], unique=True)
    op.drop_column(_TABLE, "locale")
