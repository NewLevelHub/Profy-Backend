"""merge questions locale rows into one row per question

Revision ID: e5a9f2d6c341
Revises: d1f47c8b3a95
Create Date: 2026-09-14 10:15:00.000000

Same redesign as the three prior migrations in this chain, applied to
`questions` — the highest-risk of the four content tables, since TWO other
tables FK into it: `user_responses.question_id` and `question_pairs.
question_a_id`/`question_b_id`. Both are repointed from each about-to-be-
deleted `kk` row to its `ru` twin (matched by natural key `(instrument,
"order")`) BEFORE the `kk` rows are deleted — a student's answered response,
or a pair's option link, must keep pointing at a question that still exists.

`short_text` is nullable per-question (only used by the junior forced-choice
pairs UI) — preserved as SQL NULL, not `{"ru": null}`, when genuinely absent,
same treatment as motivation_statements.text_junior in d1f47c8b3a95.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5a9f2d6c341"
down_revision: Union[str, None] = "d1f47c8b3a95"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _locale_type() -> postgresql.ENUM:
    return postgresql.ENUM("ru", "kk", name="locale_enum", create_type=False)


def upgrade() -> None:
    op.add_column("questions", sa.Column("text_i18n", postgresql.JSONB(), nullable=True))
    op.add_column("questions", sa.Column("short_text_i18n", postgresql.JSONB(), nullable=True))

    op.execute(
        """
        UPDATE questions ru SET
            text_i18n = jsonb_build_object('ru', ru.text) ||
                COALESCE(
                    (SELECT jsonb_build_object('kk', kk.text)
                     FROM questions kk
                     WHERE kk.instrument = ru.instrument AND kk."order" = ru."order" AND kk.locale = 'kk'),
                    '{}'::jsonb
                ),
            short_text_i18n = CASE WHEN ru.short_text IS NULL THEN NULL ELSE
                jsonb_build_object('ru', ru.short_text) ||
                COALESCE(
                    (SELECT jsonb_build_object('kk', kk.short_text)
                     FROM questions kk
                     WHERE kk.instrument = ru.instrument AND kk."order" = ru."order" AND kk.locale = 'kk'
                       AND kk.short_text IS NOT NULL),
                    '{}'::jsonb
                )
            END
        WHERE ru.locale = 'ru'
        """
    )

    # Repoint every FK from the about-to-be-deleted `kk` twin to the
    # surviving `ru` row, BEFORE deleting.
    op.execute(
        """
        UPDATE user_responses ur
        SET question_id = ru.id
        FROM questions kk
        JOIN questions ru
            ON ru.instrument = kk.instrument AND ru."order" = kk."order" AND ru.locale = 'ru'
        WHERE ur.question_id = kk.id AND kk.locale = 'kk'
        """
    )
    for fk_col in ("question_a_id", "question_b_id"):
        op.execute(
            f"""
            UPDATE question_pairs qp
            SET {fk_col} = ru.id
            FROM questions kk
            JOIN questions ru
                ON ru.instrument = kk.instrument AND ru."order" = kk."order" AND ru.locale = 'ru'
            WHERE qp.{fk_col} = kk.id AND kk.locale = 'kk'
            """
        )

    op.execute("DELETE FROM questions WHERE locale = 'kk'")

    op.drop_index("ix_questions_locale", table_name="questions")

    for field in ("text", "short_text"):
        op.drop_column("questions", field)
        op.alter_column("questions", f"{field}_i18n", new_column_name=field)
    op.alter_column("questions", "text", nullable=False)

    op.drop_column("questions", "locale")


def downgrade() -> None:
    op.add_column(
        "questions",
        sa.Column("locale", _locale_type(), nullable=False, server_default="ru"),
    )
    op.create_index("ix_questions_locale", "questions", ["locale"])

    op.add_column("questions", sa.Column("text_ru", sa.String(), nullable=True))
    op.add_column("questions", sa.Column("short_text_ru", sa.String(), nullable=True))
    op.execute("UPDATE questions SET text_ru = text->>'ru', short_text_ru = short_text->>'ru'")

    # `user_responses`/`question_pairs` keep pointing at the (now `ru`-only)
    # rows — the synthesized `kk` twin below is a display-only duplicate for
    # downgrade purposes, never a response/pair target (this migration is a
    # rare rollback path, not expected to round-trip losslessly). `text`/
    # `short_text` (still JSONB here) get a throwaway '{}' placeholder — the
    # real kk content goes straight into `text_ru`/`short_text_ru`.
    op.execute(
        """
        INSERT INTO questions (id, instrument, riasec_type, bigfive_domain, mi_category,
            facet, keyed, icon, "order", age_tier, locale, text, short_text,
            text_ru, short_text_ru, overrides)
        SELECT gen_random_uuid(), instrument, riasec_type, bigfive_domain, mi_category,
            facet, keyed, icon, "order", age_tier, 'kk', '{}'::jsonb, NULL,
            text->>'kk', short_text->>'kk', '{}'::jsonb
        FROM questions
        WHERE locale = 'ru' AND text ? 'kk'
        """
    )

    for field in ("text", "short_text"):
        op.drop_column("questions", field)
        op.alter_column("questions", f"{field}_ru", new_column_name=field)
    op.alter_column("questions", "text", nullable=False)
