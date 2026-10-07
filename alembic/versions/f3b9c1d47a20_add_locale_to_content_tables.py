"""add locale to bank-seeded content tables

Revision ID: f3b9c1d47a20
Revises: d80fbf5d1f43
Create Date: 2026-09-03 09:00:00.000000

KZ-301 — variant A of the content-localization plan (docs/i18n-contract.md,
CLAUDE.md "Localization"): every bank-seeded content table gets a `locale`
column so one logical content unit becomes one row per locale, keyed
`(<natural_key>, locale)`. Existing rows are Russian, so they take `locale='ru'`
from the column default. `locale_enum` already exists (migration
d80fbf5d1f43 added it for `users.locale`); this migration only reuses it.

The bare single-column UNIQUE that two of these tables carried
(`ix_motivation_pairs_pair_index`, `ix_directions_slug`) becomes a plain
lookup index plus a new composite `(natural_key, locale)` UNIQUE. The other
three tables (`questions`, `question_pairs`, `motivation_statements`) never had
a DB-level unique on their natural key — the seed scripts dedupe by
`(natural_key, locale)` in Python — so they only gain the `locale` column and
its index, no new constraint (matching KZ-301's "replace the existing unique":
there was none to replace, and adding one would newly reject fixtures that use
a "don't-care" `order=0`).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f3b9c1d47a20"
down_revision: Union[str, None] = "d80fbf5d1f43"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _locale_type() -> postgresql.ENUM:
    # Reuse the existing type; never emit CREATE/DROP TYPE from this migration.
    return postgresql.ENUM("ru", "kk", name="locale_enum", create_type=False)


# every bank-seeded content table gains the `locale` column + its index
_CONTENT_TABLES = (
    "questions",
    "question_pairs",
    "motivation_statements",
    "motivation_pairs",
    "directions",
)

# table -> (natural-key columns, existing single-key UNIQUE index to demote to
#           a plain lookup index and replace with a composite (key, locale)
#           UNIQUE constraint)
_REPLACE_UNIQUE: dict[str, tuple[list[str], str]] = {
    "motivation_pairs": (["pair_index"], "ix_motivation_pairs_pair_index"),
    "directions": (["slug"], "ix_directions_slug"),
}


def _uq_name(table: str, key_cols: list[str]) -> str:
    return f"uq_{table}_{'_'.join(key_cols)}_locale"


def upgrade() -> None:
    for table in _CONTENT_TABLES:
        # NOT NULL + server_default 'ru' backfills every existing row in one
        # pass; the seed scripts set `locale` explicitly from here on.
        op.add_column(
            table,
            sa.Column("locale", _locale_type(), nullable=False, server_default="ru"),
        )
        op.create_index(f"ix_{table}_locale", table, ["locale"])

    for table, (key_cols, old_unique_ix) in _REPLACE_UNIQUE.items():
        op.drop_index(old_unique_ix, table_name=table)
        op.create_index(old_unique_ix, table, key_cols)
        op.create_unique_constraint(
            _uq_name(table, key_cols), table, [*key_cols, "locale"]
        )


def downgrade() -> None:
    for table, (key_cols, old_unique_ix) in _REPLACE_UNIQUE.items():
        op.drop_constraint(_uq_name(table, key_cols), table, type_="unique")
        op.drop_index(old_unique_ix, table_name=table)
        op.create_index(old_unique_ix, table, key_cols, unique=True)

    for table in _CONTENT_TABLES:
        op.drop_index(f"ix_{table}_locale", table_name=table)
        op.drop_column(table, "locale")
    # `locale_enum` type is intentionally left in place — it is owned by
    # migration d80fbf5d1f43 (users.locale), not by this one.
