"""Locale-aware reads for the bank-seeded content tables (KZ-301).

The content tables (`questions`, `question_pairs`, `motivation_statements`,
`motivation_pairs`, `directions`) carry a `locale` column: one logical content
unit is one row per locale, keyed `(natural_key, locale)`, with structural
fields (order, age_tier, scoring codes, holland_code, category, …) identical
across locales — `scripts/seed_*.py` enforces that.

Two access patterns cover every read:

* **Display reads** — the text shown to the user — go through
  :func:`localized_rows`: **per-natural-key** fallback. For each logical unit,
  the requested locale's row wins; where that locale has no row for it, the
  ``DEFAULT_LOCALE`` row is used and a fallback is recorded. This stays correct
  at every stage of translation — a half-translated `kk` bank yields the
  translated rows plus `ru` for the rest, never a short set — so tickets that
  translate one instrument at a time (KZ-302…306) don't need to land together.

* **Scoring / counting** reads that only touch structural fields pin directly
  to ``DEFAULT_LOCALE`` (``Model.locale == DEFAULT_LOCALE`` in the ``where``).
  The ``ru`` set is the canonical, always-complete structural set, so a score
  or a denominator computed against it is identical to one computed against any
  translated locale and stays byte-for-byte stable regardless of the user's UI
  language. Queries that reach a content table only by joining
  ``user_responses`` need no filter at all — the join already restricts them to
  the exact rows the user answered.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import DEFAULT_LOCALE, get_locale, record_fallback

# A natural key: one column name, or a tuple of them.
KeySpec = "str | tuple[str, ...]"


def _entity(row: Any, scalars: bool) -> Any:
    """The mapped content row — `row` itself for a scalar select, its first
    element for a multi-entity `select(Model, a, b)`."""
    return row if scalars else row[0]


def _key_of(row: Any, key: "str | tuple[str, ...]", scalars: bool) -> Any:
    obj = _entity(row, scalars)
    if isinstance(key, tuple):
        return tuple(getattr(obj, k) for k in key)
    return getattr(obj, key)


async def localized_rows(
    db: AsyncSession,
    stmt: Select,
    model: Any,
    *,
    key: "str | tuple[str, ...]",
    locale: str | None = None,
    scalars: bool = True,
) -> list[Any]:
    """Run ``stmt`` for the request locale with per-``key`` fallback to
    ``DEFAULT_LOCALE``.

    ``stmt`` must NOT already constrain ``model.locale`` — this adds it. Result
    order follows the ``DEFAULT_LOCALE`` run (the canonical set), with each
    unit's row swapped for the requested locale's where one exists. ``key`` is
    the natural-key column name (or tuple) that identifies one logical unit
    across locales. ``scalars`` mirrors the caller's result handling:
    ``True`` -> ORM entities, ``False`` -> row tuples.
    """
    requested = locale or get_locale()

    ru_result = await db.execute(stmt.where(model.locale == DEFAULT_LOCALE))
    ru_rows = list(ru_result.scalars().all() if scalars else ru_result.all())
    if requested == DEFAULT_LOCALE:
        return ru_rows

    loc_result = await db.execute(stmt.where(model.locale == requested))
    loc_rows = loc_result.scalars().all() if scalars else loc_result.all()
    loc_by_key = {_key_of(r, key, scalars): r for r in loc_rows}

    out: list[Any] = []
    missing = False
    for row in ru_rows:
        translated = loc_by_key.get(_key_of(row, key, scalars))
        if translated is not None:
            out.append(translated)
        else:
            out.append(row)
            missing = True
    if missing:
        record_fallback(requested)
    return out
