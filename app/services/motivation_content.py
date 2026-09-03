"""
Motivation methodology reference — locale-aware accessors over
`app/i18n/catalog/motivation.py` (KZ-307). Mirrors `bigfive_content.py`'s role.
"""

from app.i18n.catalog import tr


def motivation_labels() -> dict[str, str]:
    """Admin/debug value label per motivation category — raw per-category
    scores are never shown to the student (TZ_Profi.md §18.3)."""
    return tr("motivation")["labels"]


def motivation_label(code: str) -> str:
    labels = motivation_labels()
    return labels.get(code, code)


def highlight_phrases(top: list[str]) -> list[str]:
    # No shared lead-in ("Тебя больше всего драйвит — ") repeated per item —
    # with 2-3 top categories that reads as the same sentence stuttering. The
    # "what this list is" framing belongs once, at the section level (frontend
    # heading), not per phrase.
    phrases = tr("motivation")["drivers"]
    return [phrases[c] for c in top if c in phrases]
