"""
MI (Multiple-Intelligences-style) methodology reference — locale-aware
accessors over `app/i18n/catalog/mi.py` (KZ-307). Junior's (6-9) replacement
for RIASEC, fixed by the model (8 categories). See app/services/mi_service.py.
"""

from app.i18n.catalog import tr


def mi_labels() -> dict[str, str]:
    """MI category name per key."""
    return tr("mi")["labels"]


def mi_strength_phrases() -> dict[str, str]:
    """Short strength-observation sentence per MI category — richer than the
    bare `mi_labels()` name."""
    return tr("mi")["strength_phrases"]


def mi_activities() -> dict[str, list[str]]:
    """Kid-friendly clubs/activities per category — junior gets no professions
    (TZ_Profi.md §4.1), only "что стоит попробовать"."""
    return tr("mi")["activities"]
