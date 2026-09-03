"""Locale-aware reads for the bank-seeded content tables (KZ-301).

The content tables (`questions`, `question_pairs`, `motivation_statements`,
`motivation_pairs`, `directions`) carry a `locale` column: one logical content
unit is one row per locale, keyed `(natural_key, locale)`, with structural
fields (order, age_tier, scoring codes, holland_code, category, …) identical
across locales — `scripts/seed_*.py` enforces that.

Two access patterns cover every read:

* **Display reads** — the text shown to the user — go through
  :func:`localized_rows`: request locale, whole-set fallback to
  ``DEFAULT_LOCALE`` when the requested locale has no rows for that query. A
  partial ``kk`` set never happens: the banks seed ``kk`` as a complete set per
  logical group or not at all, so "no ``kk`` rows for this query" always means
  "``kk`` isn't translated here", and the whole ``ru`` set is the right answer.

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


def _fallback_chain(locale: str) -> tuple[str, ...]:
    if locale == DEFAULT_LOCALE:
        return (DEFAULT_LOCALE,)
    return (locale, DEFAULT_LOCALE)


async def localized_rows(
    db: AsyncSession,
    stmt: Select,
    locale_column: Any,
    *,
    locale: str | None = None,
    scalars: bool = True,
) -> list[Any]:
    """Run ``stmt`` filtered to ``locale`` (default: the request locale).

    Falls back to the full ``DEFAULT_LOCALE`` set — recording an i18n fallback —
    when the requested locale yields no rows. ``scalars`` mirrors the caller's
    own result handling: ``True`` -> ``result.scalars().all()`` (ORM entities),
    ``False`` -> ``result.all()`` (row tuples from a multi-entity select).
    """
    requested = locale or get_locale()
    for candidate in _fallback_chain(requested):
        result = await db.execute(stmt.where(locale_column == candidate))
        rows = list(result.scalars().all() if scalars else result.all())
        if rows:
            if candidate != requested:
                record_fallback(requested)
            return rows
    return []
