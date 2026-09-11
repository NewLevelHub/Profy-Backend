"""Translations for free-text *data* strings that live inside JSONB blobs.

The `*_i18n` sibling-column pattern (`resolve_column_i18n`, KZ-501) covers text
that has its own column — `University.description`, `Program.name`. It does not
cover the free text buried inside `Program.requirements`: `notes`,
`exams`, `source_required_documents`, `extracurriculars`, and the `name` /
`conditions` of each entry in `Program.grants`. Those are the strings the
university/program screen renders as its admission-requirement cards, and they
were still Russian on a `kk` screen under an otherwise Kazakh heading.

A per-row `requirements_i18n` column would have been the obvious symmetry, and
it is the wrong shape here: the catalog holds ~12.4k programs but only ~4.6k
*distinct* requirement strings, because the same phrase ("Портфолио творческих
работ", "Математика") repeats across hundreds of programs. So the translation
is keyed by the **source string**, not by the row — one entry per distinct
phrase, shared by every program that uses it.

The dictionary is a committed JSON file, not a table: it is static reference
data that ships with the image, is reviewed in git like the rest of the content
banks, and needs no migration or seed step. It is produced and refreshed by
`scripts/apply_requirements_kk.py` (dump → translate → merge).

Lookup is exact-match on the trimmed source string. A miss returns the source
unchanged (never blank, never a key — contract §5) and is tallied as a
locale→ru fallback, so the coverage gap is visible in metrics rather than
silently rendering Russian.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.i18n import DEFAULT_LOCALE, get_locale, record_fallback

_DATA_DIR = Path(__file__).resolve().parent / "data"

# One file per locale. `ru` has none — it is the source side of every entry.
_FILENAME = "program_requirements_{locale}.json"


@lru_cache(maxsize=None)
def _dictionary(locale: str) -> dict[str, str]:
    """`{source string: translation}` for one locale, or empty if absent.

    Cached: the file is read once per locale per process. A missing file is a
    legitimate state (a locale nobody has translated yet), not an error.
    """
    path = _DATA_DIR / _FILENAME.format(locale=locale)
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    # Keys are normalized on write, but normalize on read too so a hand-edited
    # file with stray whitespace still resolves.
    return {str(k).strip(): str(v) for k, v in raw.items() if str(v).strip()}


def translate_data_string(text: str | None, *, locale: str | None = None) -> str | None:
    """One catalog data string in the request locale, or unchanged on a miss.

    `None`/blank passes through untouched — "no data" must stay distinguishable
    from "translated to nothing".
    """
    if not text:
        return text
    loc = locale or get_locale()
    if loc == DEFAULT_LOCALE:
        return text

    translated = _dictionary(loc).get(text.strip())
    if translated:
        return translated
    record_fallback(loc)
    return text


def translate_data_list(
    values: list[str] | None, *, locale: str | None = None
) -> list[str]:
    """`translate_data_string` over a list, preserving order and length.

    Order matters: these lists are rendered as-is, and several of them are
    paired positionally with other fields at the call site.
    """
    if not values:
        return []
    loc = locale or get_locale()
    return [translate_data_string(v, locale=loc) or v for v in values]
