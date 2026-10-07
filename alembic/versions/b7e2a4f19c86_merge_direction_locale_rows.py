"""merge directions locale rows into one row per direction

Revision ID: b7e2a4f19c86
Revises: f4a1b8c6e2d7
Create Date: 2026-09-14 10:00:00.000000

Reverts the "variant A" (one physical row per locale, KZ-301/f3b9c1d47a20) shape
for `directions` in favor of one logical direction = one row, with the
localizable fields (`name`, `description`, `professions`, `skills_needed`,
`subjects_to_develop`, `first_steps`) stored as `{"ru": ..., "kk": ...}` JSONB
maps read via `app.i18n.pick_locale`/`pick_locale_list`. See
docs/i18n-contract.md §8 and the KZ-301-duplication cleanup plan.

`directions` has no inbound foreign keys (only ever joined by `slug`), so this
is the simplest of the four content tables being converted — no FK remap
needed, just: fold each `ru`/`kk` pair into one row keyed by `slug`, drop the
`kk` twin, drop `locale`.

Downgrade is best-effort: it recreates the `locale` column/shape and splits
each row back into a `ru` row (kept) plus a synthesized `kk` row from the `kk`
key of each JSONB map when present. Any admin `overrides` recorded after the
upgrade are NOT split back per-locale (the override shape itself changed) —
acceptable for a destructive-merge migration's rollback path, not intended to
round-trip losslessly.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7e2a4f19c86"
down_revision: Union[str, None] = "f4a1b8c6e2d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON_FIELDS = ("name", "description", "professions", "skills_needed", "subjects_to_develop", "first_steps")


def _locale_type() -> postgresql.ENUM:
    return postgresql.ENUM("ru", "kk", name="locale_enum", create_type=False)


def upgrade() -> None:
    for field in _JSON_FIELDS:
        op.add_column("directions", sa.Column(f"{field}_i18n", postgresql.JSONB(), nullable=True))

    merge_sql = " ".join(
        f"""
        {field}_i18n = jsonb_build_object('ru', ru.{field}) ||
            COALESCE(
                (SELECT jsonb_build_object('kk', kk.{field})
                 FROM directions kk WHERE kk.slug = ru.slug AND kk.locale = 'kk'),
                '{{}}'::jsonb
            ){',' if field != _JSON_FIELDS[-1] else ''}
        """
        for field in _JSON_FIELDS
    )
    op.execute(f"UPDATE directions ru SET {merge_sql} WHERE ru.locale = 'ru'")

    op.execute("DELETE FROM directions WHERE locale = 'kk'")

    op.drop_constraint("uq_directions_slug_locale", "directions", type_="unique")
    op.drop_index("ix_directions_locale", table_name="directions")
    op.drop_index("ix_directions_slug", table_name="directions")

    for field in _JSON_FIELDS:
        op.drop_column("directions", field)
        op.alter_column("directions", f"{field}_i18n", new_column_name=field)
        op.alter_column("directions", field, nullable=False)

    op.drop_column("directions", "locale")
    op.create_index("ix_directions_slug", "directions", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_directions_slug", table_name="directions")
    op.add_column(
        "directions",
        sa.Column("locale", _locale_type(), nullable=False, server_default="ru"),
    )
    op.create_index("ix_directions_locale", "directions", ["locale"])
    op.create_index("ix_directions_slug", "directions", ["slug"])
    op.create_unique_constraint("uq_directions_slug_locale", "directions", ["slug", "locale"])

    for field in _JSON_FIELDS:
        old_type = sa.Text() if field in ("name", "description") else postgresql.JSONB()
        op.add_column("directions", sa.Column(f"{field}_ru", old_type, nullable=True))

    ru_assign = ", ".join(f"{field}_ru = {field}->>'ru'" if field in ("name", "description") else f"{field}_ru = {field}->'ru'" for field in _JSON_FIELDS)
    op.execute(f"UPDATE directions SET {ru_assign}")

    # Synthesize the `kk` twin row (only where a `kk` value actually exists),
    # BEFORE the JSONB map columns are dropped below. The real kk content
    # goes straight into the `_ru`-suffixed columns (what survives the
    # rename); the still-live JSONB columns just get a throwaway placeholder
    # satisfying their NOT NULL constraint (`name`) since they're dropped
    # right after — writing the kk text into them here would just wrap it as
    # a JSON string scalar, not the plain value the renamed column expects.
    kk_select = ", ".join(
        (f"{f}->>'kk'" if f in ("name", "description") else f"COALESCE({f}->'kk', '[]'::jsonb)")
        for f in _JSON_FIELDS
    )
    kk_ru_cols = ", ".join(f"{f}_ru" for f in _JSON_FIELDS)
    # All 6 fields are still JSONB at this point (dropped right after) —
    # the actual placeholder value is irrelevant, it just needs to be valid
    # jsonb and satisfy `name`'s NOT NULL.
    placeholder_cols = ", ".join("'{}'::jsonb" for _ in _JSON_FIELDS)
    op.execute(
        f"""
        INSERT INTO directions (id, slug, holland_code, locale,
            name, description, professions, skills_needed, subjects_to_develop, first_steps,
            {kk_ru_cols}, overrides)
        SELECT gen_random_uuid(), slug, holland_code, 'kk',
            {placeholder_cols},
            {kk_select},
            '{{}}'::jsonb
        FROM directions
        WHERE locale = 'ru' AND name ? 'kk'
        """
    )

    for field in _JSON_FIELDS:
        op.drop_column("directions", field)
        op.alter_column("directions", f"{field}_ru", new_column_name=field)

    op.alter_column("directions", "name", nullable=False)
    op.alter_column("directions", "description", nullable=False, server_default="")
    op.alter_column("directions", "professions", nullable=False, server_default="[]")
    op.alter_column("directions", "skills_needed", nullable=False, server_default="[]")
    op.alter_column("directions", "subjects_to_develop", nullable=False, server_default="[]")
    op.alter_column("directions", "first_steps", nullable=False, server_default="[]")
