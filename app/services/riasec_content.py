"""
RIASEC methodology reference — locale-aware accessors over
`app/i18n/catalog/riasec.py` (KZ-307). Fixed by the model itself (6 types),
not "question bank" content; the strings live in the catalog so `ru`/`kk`
resolve through the request locale (with a `ru` fallback). The frontend keeps
its own UI copy (`RIASEC_LABELS` in `shared/config/constants.ts`).

Each accessor returns the whole table for the current request locale — call it
at use time, don't cache the result across a request whose locale may differ.
"""

from app.i18n.catalog import tr


def riasec_labels() -> dict[str, str]:
    """RIASEC type name per Holland letter (R..C)."""
    return tr("riasec")["labels"]


def likert_labels() -> list[str]:
    """The fixed 1-5 liking scale every RIASEC question is answered on. Also
    reused by the direction-fit inquiry feature."""
    return tr("riasec")["likert"]


def riasec_strength_phrases() -> dict[str, str]:
    """Short strength-observation sentence per Holland type — richer than the
    bare `riasec_labels()` name. Evidence text for fallback strength cards."""
    return tr("riasec")["strength_phrases"]


def neutral_career_why_variants() -> list[str]:
    """Honest "ranked by the overall pattern, not a specific strength"
    disclosures for a matched career with no evidenced Holland overlap —
    several rephrasings so a flat profile's 5-10 fallbacks don't read
    copy-pasted (result-quality-fixes.md §3)."""
    return tr("riasec")["neutral_why"]


def neutral_career_why() -> str:
    """The first, most-established phrasing — for callers that only need *a*
    neutral fallback string, not the rotation."""
    return tr("riasec")["neutral_why"][0]


def neutral_try_now() -> str:
    """Safe non-empty `try_now` for a Direction with no `first_steps`."""
    return tr("riasec")["neutral_try_now"]


def type_activities() -> dict[str, list[str]]:
    """Methodology §5.4 — extracurricular activities per type, for `reinforce`
    / `compensate` in the development plan."""
    return tr("riasec")["activities"]
