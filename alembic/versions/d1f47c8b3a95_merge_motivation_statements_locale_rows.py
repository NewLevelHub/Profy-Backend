"""merge motivation_statements locale rows into one row per statement

Revision ID: d1f47c8b3a95
Revises: c9d3b6a082f5
Create Date: 2026-09-14 10:10:00.000000

Same redesign as b7e2a4f19c86 (directions) / c9d3b6a082f5 (motivation_pairs),
applied to `motivation_statements` — the first of the four content tables in
this cleanup that has an inbound foreign key: `motivation_responses.
most_statement_id`/`least_statement_id` point at a specific locale's physical
row. Those FKs are repointed at the surviving `ru` row (per natural key
`(triplet_index, order)`) BEFORE the `kk` twin rows are deleted, so no
response loses its target.

`text_junior` is nullable per-statement (not every statement has a junior
rewording) — the merge preserves a genuinely absent value as SQL NULL rather
than `{"ru": null}`, so `pick_locale`/callers keep seeing "no junior text"
exactly as before, not a mapping with a null value in it.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d1f47c8b3a95"
down_revision: Union[str, None] = "c9d3b6a082f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _locale_type() -> postgresql.ENUM:
    return postgresql.ENUM("ru", "kk", name="locale_enum", create_type=False)


def upgrade() -> None:
    op.add_column("motivation_statements", sa.Column("text_i18n", postgresql.JSONB(), nullable=True))
    op.add_column("motivation_statements", sa.Column("text_junior_i18n", postgresql.JSONB(), nullable=True))

    op.execute(
        """
        UPDATE motivation_statements ru SET
            text_i18n = jsonb_build_object('ru', ru.text) ||
                COALESCE(
                    (SELECT jsonb_build_object('kk', kk.text)
                     FROM motivation_statements kk
                     WHERE kk.triplet_index = ru.triplet_index AND kk."order" = ru."order" AND kk.locale = 'kk'),
                    '{}'::jsonb
                ),
            text_junior_i18n = CASE WHEN ru.text_junior IS NULL THEN NULL ELSE
                jsonb_build_object('ru', ru.text_junior) ||
                COALESCE(
                    (SELECT jsonb_build_object('kk', kk.text_junior)
                     FROM motivation_statements kk
                     WHERE kk.triplet_index = ru.triplet_index AND kk."order" = ru."order" AND kk.locale = 'kk'
                       AND kk.text_junior IS NOT NULL),
                    '{}'::jsonb
                )
            END
        WHERE ru.locale = 'ru'
        """
    )

    # Repoint FKs from the about-to-be-deleted `kk` twin to the surviving
    # `ru` row, BEFORE deleting — a response answered while the DB still had
    # a `kk` row would otherwise lose its target statement.
    for fk_col in ("most_statement_id", "least_statement_id"):
        op.execute(
            f"""
            UPDATE motivation_responses mr
            SET {fk_col} = ru.id
            FROM motivation_statements kk
            JOIN motivation_statements ru
                ON ru.triplet_index = kk.triplet_index AND ru."order" = kk."order" AND ru.locale = 'ru'
            WHERE mr.{fk_col} = kk.id AND kk.locale = 'kk'
            """
        )

    op.execute("DELETE FROM motivation_statements WHERE locale = 'kk'")

    op.drop_index("ix_motivation_statements_locale", table_name="motivation_statements")

    for field in ("text", "text_junior"):
        op.drop_column("motivation_statements", field)
        op.alter_column("motivation_statements", f"{field}_i18n", new_column_name=field)
    op.alter_column("motivation_statements", "text", nullable=False)

    op.drop_column("motivation_statements", "locale")


def downgrade() -> None:
    op.add_column(
        "motivation_statements",
        sa.Column("locale", _locale_type(), nullable=False, server_default="ru"),
    )
    op.create_index("ix_motivation_statements_locale", "motivation_statements", ["locale"])

    op.add_column("motivation_statements", sa.Column("text_ru", sa.String(), nullable=True))
    op.add_column("motivation_statements", sa.Column("text_junior_ru", sa.String(), nullable=True))
    op.execute(
        "UPDATE motivation_statements SET text_ru = text->>'ru', text_junior_ru = text_junior->>'ru'"
    )

    # motivation_responses keeps pointing at the (now `ru`-only) rows — the
    # synthesized `kk` twin below is a display-only duplicate for downgrade
    # purposes, never a response target (this migration is a rare rollback
    # path, not expected to round-trip losslessly). `text`/`text_junior`
    # (still JSONB at this point) get a throwaway placeholder — the real kk
    # content goes straight into `text_ru`/`text_junior_ru`, which is what
    # survives the column rename below.
    op.execute(
        """
        INSERT INTO motivation_statements (id, triplet_index, "order", category, locale,
            text, text_junior, text_ru, text_junior_ru, overrides)
        SELECT gen_random_uuid(), triplet_index, "order", category, 'kk',
            '{}'::jsonb, NULL, text->>'kk', text_junior->>'kk', '{}'::jsonb
        FROM motivation_statements
        WHERE locale = 'ru' AND text ? 'kk'
        """
    )

    for field in ("text", "text_junior"):
        op.drop_column("motivation_statements", field)
        op.alter_column("motivation_statements", f"{field}_ru", new_column_name=field)
    op.alter_column("motivation_statements", "text", nullable=False)
