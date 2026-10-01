"""merge question_pairs locale rows into one row per pair

Revision ID: f7c1e9b4a608
Revises: e5a9f2d6c341
Create Date: 2026-09-14 10:20:00.000000

Last of the four content-table merges. Must run AFTER e5a9f2d6c341
(`questions`) — that migration already repointed every `question_pairs.
question_a_id`/`question_b_id` from a `kk`-question row to its merged `ru`
twin, regardless of which locale the *pair* row itself belongs to. So by the
time this migration runs, a pair's `ru` and `kk` twin rows already agree on
`question_a_id`/`question_b_id` — no further FK work needed here, just merge
the display fields and drop the twin.

Localized fields: `frame`, `option_a_text`, `option_b_text` (all nullable —
preserved as SQL NULL when genuinely absent, not `{"ru": null}`).
`option_a_icon`/`option_b_icon` are NOT localized (shared emoji, per
scripts/question_pairing.py) and are untouched by this migration. Nothing FKs
to `question_pairs.id`, so no downstream repoint is needed for this table
itself.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f7c1e9b4a608"
down_revision: Union[str, None] = "e5a9f2d6c341"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TEXT_FIELDS = ("frame", "option_a_text", "option_b_text")


def _locale_type() -> postgresql.ENUM:
    return postgresql.ENUM("ru", "kk", name="locale_enum", create_type=False)


def _merge_expr(field: str) -> str:
    return f"""{field}_i18n = CASE WHEN ru.{field} IS NULL THEN NULL ELSE
        jsonb_build_object('ru', ru.{field}) ||
        COALESCE(
            (SELECT jsonb_build_object('kk', kk.{field})
             FROM question_pairs kk
             WHERE kk.instrument = ru.instrument AND kk.pair_index = ru.pair_index AND kk.locale = 'kk'
               AND kk.{field} IS NOT NULL),
            '{{}}'::jsonb
        )
    END"""


def upgrade() -> None:
    for field in _TEXT_FIELDS:
        op.add_column("question_pairs", sa.Column(f"{field}_i18n", postgresql.JSONB(), nullable=True))

    merge_sql = ", ".join(_merge_expr(field) for field in _TEXT_FIELDS)
    op.execute(f"UPDATE question_pairs ru SET {merge_sql} WHERE ru.locale = 'ru'")

    op.execute("DELETE FROM question_pairs WHERE locale = 'kk'")

    op.drop_index("ix_question_pairs_locale", table_name="question_pairs")

    for field in _TEXT_FIELDS:
        op.drop_column("question_pairs", field)
        op.alter_column("question_pairs", f"{field}_i18n", new_column_name=field)

    op.drop_column("question_pairs", "locale")


def downgrade() -> None:
    op.add_column(
        "question_pairs",
        sa.Column("locale", _locale_type(), nullable=False, server_default="ru"),
    )
    op.create_index("ix_question_pairs_locale", "question_pairs", ["locale"])

    for field in _TEXT_FIELDS:
        op.add_column("question_pairs", sa.Column(f"{field}_ru", sa.String(), nullable=True))
    op.execute(
        "UPDATE question_pairs SET " + ", ".join(f"{f}_ru = {f}->>'ru'" for f in _TEXT_FIELDS)
    )

    # `question_a_id`/`question_b_id` on the synthesized `kk` twin point at
    # the same (merged) Question rows as the `ru` row — there is no separate
    # `kk`-locale Question row to point at post-downgrade of e5a9f2d6c341's
    # own downgrade path unless that migration is downgraded too; this is a
    # display-only duplicate, not expected to be scored against.
    placeholder_cols = ", ".join("'{}'::jsonb" for _ in _TEXT_FIELDS)
    kk_select = ", ".join(f"{f}->>'kk'" for f in _TEXT_FIELDS)
    kk_ru_cols = ", ".join(f"{f}_ru" for f in _TEXT_FIELDS)
    op.execute(
        f"""
        INSERT INTO question_pairs (id, instrument, age_tier, pair_index,
            question_a_id, question_b_id, option_a_icon, option_b_icon, locale,
            frame, option_a_text, option_b_text, {kk_ru_cols}, overrides)
        SELECT gen_random_uuid(), instrument, age_tier, pair_index,
            question_a_id, question_b_id, option_a_icon, option_b_icon, 'kk',
            {placeholder_cols},
            {kk_select}, '{{}}'::jsonb
        FROM question_pairs
        WHERE locale = 'ru' AND (frame ? 'kk' OR option_a_text ? 'kk' OR option_b_text ? 'kk')
        """
    )

    for field in _TEXT_FIELDS:
        op.drop_column("question_pairs", field)
        op.alter_column("question_pairs", f"{field}_ru", new_column_name=field)
