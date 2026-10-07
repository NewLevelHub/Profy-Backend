"""Translated city names — for catalogue search only (PRO-450).

`University.city` holds one Russian string, and by contract (§13, KZ-502) city
and country get no `*_i18n` overlay: the frontend localizes them for display
from its own dictionary (`Profy-Frontend/src/shared/i18n/geo.ts`, `CITY_KK`).
So the kk screen shows «Өскемен», while the column says «Усть-Каменогорск» — and
a student typing what they see found nothing.

This is the same dictionary, keyed by the source (ru) string like
`program_requirements_kk.json`, used the other way round: the search text is
matched against the translations and the ru names behind the hits are what
the query filters on. `app/i18n/data/geo_cities_kk.json` mirrors `CITY_KK`
entry for entry — change both together, or display and search disagree.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES

_DATA_DIR = Path(__file__).resolve().parent / "data"
_FILENAME = "geo_cities_{locale}.json"


@lru_cache(maxsize=None)
def _cities(locale: str) -> dict[str, str]:
    """`{ru city: translation}` for one locale, or empty if there is no file."""
    path = _DATA_DIR / _FILENAME.format(locale=locale)
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    return {str(k).strip(): str(v).strip() for k, v in raw.items() if str(v).strip()}


def source_cities_matching(text: str) -> list[str]:
    """Russian city names whose translation, in any supported locale,
    contains `text` (case-insensitive) — «өске» → ["Усть-Каменогорск"].

    Every locale is searched whatever the request locale, as with translated
    university names: a city is found by any name it is shown under.
    """
    needle = text.strip().casefold()
    if not needle:
        return []
    return sorted({
        source
        for locale in SUPPORTED_LOCALES
        if locale != DEFAULT_LOCALE
        for source, translated in _cities(locale).items()
        if needle in translated.casefold()
    })
