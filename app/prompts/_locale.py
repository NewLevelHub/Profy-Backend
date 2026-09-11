"""Prompt localization directives and Kazakh terminology glossary (KZ-401).

Centralizes model language instructions and terminology enforcement for all LLM
prompts (report narrative, goal roadmap, direction roadmap, direction inquiry).

KZ-401 acceptance criteria:
- No prompt builder hardcodes "русский" / "Язык ответа" — only language_directive(locale).
- When locale == "kk", prompts include the Kazakh language instruction and glossary.
- When locale == "ru", output matches byte-for-byte with the previous Russian prompt.
- Profession terminology is synchronized with KZ-306 (scripts/data/direction_glossary_kk.json).
"""
from __future__ import annotations

import functools
import json
import logging
from pathlib import Path
from typing import Any

from app.i18n import DEFAULT_LOCALE

logger = logging.getLogger(__name__)

_GLOSSARY_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "scripts"
    / "data"
    / "direction_glossary_kk.json"
)

# Standard English/Latin profession names and fixed translations from KZ-306
_LATIN_PROFESSION_TERMS: list[tuple[str, str]] = [
    ("Data Engineer", "Data Engineer"),
    ("DevOps-инженер", "DevOps-инженер"),
    ("Mobile-разработчик", "Mobile-әзірлеуші"),
    ("UX/UI-дизайнер", "UX/UI-дизайнер"),
    ("QA-инженер (тестировщик)", "QA-инженер (тестілеуші)"),
    ("HR-менеджер", "HR-менеджер"),
    ("Event-менеджер", "Event-менеджер"),
    ("PR-менеджер", "PR-менеджер"),
    ("Аниматор (2D/3D)", "Аниматор (2D/3D)"),
]


def language_directive(locale: str) -> str:
    """Explicit model instruction enforcing response language."""
    if locale == "kk":
        return (
            "Жауапты тек қазақ тілінде бер. "
            "Орыс немесе ағылшын сөздерін қолданба (кірме терминдерден басқа)."
        )
    return "Язык ответа — русский."


@functools.lru_cache(maxsize=1)
def load_direction_glossary() -> dict[str, dict[str, Any]]:
    """Load direction glossary mapping slug -> entry from KZ-306 dataset."""
    if _GLOSSARY_PATH.exists():
        try:
            with open(_GLOSSARY_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return {item["slug"]: item for item in data if "slug" in item}
        except Exception as e:
            logger.warning("Failed to load direction glossary from %s: %s", _GLOSSARY_PATH, e)

    # Fallback to Python source of truth in scripts/riasec_professions.py
    try:
        from scripts.riasec_professions import KK_NAMES, PROFESSIONS
        from app.models.direction import slugify

        result: dict[str, dict[str, Any]] = {}
        for p in PROFESSIONS:
            title_ru = p["title"]
            slug = slugify(title_ru)
            if slug not in result:
                result[slug] = {
                    "slug": slug,
                    "holland_code": p.get("holland_code", ""),
                    "name_ru": title_ru,
                    "name_kk": KK_NAMES.get(title_ru, title_ru),
                }
        return result
    except Exception as e:
        logger.warning("Failed to load fallback glossary from riasec_professions: %s", e)
        return {}


def get_direction_name_kk(slug: str) -> str | None:
    """Lookup the official Kazakh direction name by slug."""
    entry = load_direction_glossary().get(slug)
    if entry:
        return entry.get("name_kk")
    return None


def glossary_block(locale: str, direction_slug: str | None = None) -> str:
    """Glossary and naming rules for prompt construction.

    Returns an empty string for Russian (locale == "ru") to preserve prompt byte-parity.
    For Kazakh (locale == "kk"), returns rules for university names, admission terms,
    and Latin/English profession terms.
    """
    if locale != "kk":
        return ""

    # Admission-term pairs come from the single backend catalog (KZ-503) so the
    # prompt rule can't drift from the rest of the codebase.
    from app.i18n.catalog import tr as _tr

    _ru_terms = _tr("subjects", locale="ru")["admission_terms"]
    _kk_terms = _tr("subjects", locale="kk")["admission_terms"]
    _term_rule = ", ".join(
        f"«{_ru_terms[key]}» орнына «{_kk_terms[key]}»"
        for key in ("ent", "profile_subjects", "threshold_score")
    )

    lines = [
        "ГЛОССАРИЙ ЖӘНЕ АТАУЛАР ЕРЕЖЕСІ:",
        "1. Университеттердің ресми атауларын транслитерациялама, өзгертпей сақта "
        "(мысалы: «Nazarbayev University», «СДУ», «ҚБТУ» және т.б.).",
        f"2. Қабылдау науқанының терминдері: {_term_rule}.",
        "3. Ғылыми және техникалық терминдердің дәлдігін сақта.",
        "4. Кәсіптердің бекітілген қазақша атауларын қатаң қолдан:",
    ]

    for ru_term, kk_term in _LATIN_PROFESSION_TERMS:
        lines.append(f"   - {ru_term} → {kk_term}")

    if direction_slug:
        entry = load_direction_glossary().get(direction_slug)
        if entry and entry.get("name_kk"):
            lines.append(
                f"   - Мақсатты бағыт атауы: «{entry['name_kk']}» "
                f"(орысша: «{entry.get('name_ru', '')}»)"
            )

    return "\n".join(lines)
