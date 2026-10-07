"""merge motivation_pairs locale rows into one row per pair

Revision ID: c9d3b6a082f5
Revises: b7e2a4f19c86
Create Date: 2026-09-14 10:05:00.000000

Same redesign as b7e2a4f19c86 (directions), applied to `motivation_pairs`:
one logical pair = one row, `text_a`/`text_b` become `{"ru": ..., "kk": ...}`
JSONB maps. Nothing FKs to `motivation_pairs.id`
(`motivation_pair_responses` is keyed by `pair_index`/`category`/`side`, not
a row id — see app/models/motivation_pair.py), so this is a plain merge, no
FK remap needed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9d3b6a082f5"
down_revision: Union[str, None] = "b7e2a4f19c86"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TEXT_FIELDS = ("text_a", "text_b")


def _locale_type() -> postgresql.ENUM:
    return postgresql.ENUM("ru", "kk", name="locale_enum", create_type=False)


def upgrade() -> None:
    for field in _TEXT_FIELDS:
        op.add_column("motivation_pairs", sa.Column(f"{field}_i18n", postgresql.JSONB(), nullable=True))

    merge_sql = ", ".join(
        f"""{field}_i18n = jsonb_build_object('ru', ru.{field}) ||
            COALESCE(
                (SELECT jsonb_build_object('kk', kk.{field})
                 FROM motivation_pairs kk WHERE kk.pair_index = ru.pair_index AND kk.locale = 'kk'),
                '{{}}'::jsonb
            )"""
        for field in _TEXT_FIELDS
    )
    op.execute(f"UPDATE motivation_pairs ru SET {merge_sql} WHERE ru.locale = 'ru'")

    op.execute("DELETE FROM motivation_pairs WHERE locale = 'kk'")

    op.drop_constraint("uq_motivation_pairs_pair_index_locale", "motivation_pairs", type_="unique")
    op.drop_index("ix_motivation_pairs_locale", table_name="motivation_pairs")
    op.drop_index("ix_motivation_pairs_pair_index", table_name="motivation_pairs")

    for field in _TEXT_FIELDS:
        op.drop_column("motivation_pairs", field)
        op.alter_column("motivation_pairs", f"{field}_i18n", new_column_name=field)
        op.alter_column("motivation_pairs", field, nullable=False)

    op.drop_column("motivation_pairs", "locale")
    op.create_unique_constraint(
        "uq_motivation_pairs_pair_index", "motivation_pairs", ["pair_index"]
    )
    op.create_index("ix_motivation_pairs_pair_index", "motivation_pairs", ["pair_index"])


def downgrade() -> None:
    op.drop_index("ix_motivation_pairs_pair_index", table_name="motivation_pairs")
    op.drop_constraint("uq_motivation_pairs_pair_index", "motivation_pairs", type_="unique")

    op.add_column(
        "motivation_pairs",
        sa.Column("locale", _locale_type(), nullable=False, server_default="ru"),
    )
    op.create_index("ix_motivation_pairs_locale", "motivation_pairs", ["locale"])
    op.create_index("ix_motivation_pairs_pair_index", "motivation_pairs", ["pair_index"])
    op.create_unique_constraint(
        "uq_motivation_pairs_pair_index_locale", "motivation_pairs", ["pair_index", "locale"]
    )

    for field in _TEXT_FIELDS:
        op.add_column("motivation_pairs", sa.Column(f"{field}_ru", sa.String(), nullable=True))
    ru_assign = ", ".join(f"{f}_ru = {f}->>'ru'" for f in _TEXT_FIELDS)
    op.execute(f"UPDATE motivation_pairs SET {ru_assign}")

    # `text_a`/`text_b` (still JSONB at this point) get a throwaway '{}'
    # placeholder — the real kk content goes into `text_a_ru`/`text_b_ru`,
    # which is what survives the column rename below.
    op.execute(
        """
        INSERT INTO motivation_pairs (id, pair_index, category_a, category_b, locale,
            text_a, text_b, text_a_ru, text_b_ru, overrides)
        SELECT gen_random_uuid(), pair_index, category_a, category_b, 'kk',
            '{}'::jsonb, '{}'::jsonb, text_a->>'kk', text_b->>'kk', '{}'::jsonb
        FROM motivation_pairs
        WHERE locale = 'ru' AND text_a ? 'kk'
        """
    )

    for field in _TEXT_FIELDS:
        op.drop_column("motivation_pairs", field)
        op.alter_column("motivation_pairs", f"{field}_ru", new_column_name=field)
        op.alter_column("motivation_pairs", field, nullable=False)
