"""Static, hand-verified resource catalogue for the roadmap's "Дополнительный
источник" block.

Every entry was opened and checked by hand (title/topic actually matches, link
resolves, not paywalled/dead/off-topic) — see the product's resource-research
checklist. The entries themselves (title/kind/url) live in
`app/i18n/catalog/resource_catalog.py` so `kind` resolves per request locale
(KZ-307); this module is just the deterministic keyword matcher.

Deliberately NOT LLM-driven, same principle as `Program.direction_slugs`
tagging: with a small, static, hand-picked set of links, a keyword match is
both simpler and more auditable. `match_category` returns None (no resources
attached) rather than guessing when nothing scores.
"""

from app.i18n.catalog import tr

# CATEGORY_KEYWORDS: match Russian substrings inside a direction's name/skills
# text to pick a resource category. This is match-data, NOT user-facing copy —
# excluded from the KZ-602 "no Cyrillic in content services" guard, same as the
# `_*_KEYS` sets in gap_analysis_service. Roadmap generation feeds this the `ru`
# direction text (roadmap gen is `ru`-locked until KZ-401/403), so the keywords
# stay Russian.
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "tech": [
        "программист", "разработчик", "разработк", "информатик", "робот",
        "инженер", "дата-аналитик", "аналитик данных", "software", "backend",
        "frontend", "it-", " it ", "компьютер", "алгоритм",
    ],
    "creative_design": [
        "архитект", "дизайн", "модельер", "иллюстрат", "художн", "творч",
        "мода", "стиль", "рисун", "живопис",
    ],
    "medicine": [
        "врач", "медицин", "медсестра", "медбрат", "биотехнолог",
        "фармацевт", "биолог", "здоровь", "стоматолог",
    ],
    "business": [
        "бизнес", "маркетинг", "финанс", "экономист", "предпринимат",
        "менеджер", "продаж", "банк",
    ],
    "humanities": [
        "журналист", "психолог", "hr", "pr-", "лингвист", "филолог",
        "писатель", "редактор", "переводчик",
    ],
    "law": [
        "юрист", "право", "следовател", "дипломат", "госслужащ",
        "адвокат", "судья", "нотариус",
    ],
    "sport": [
        "спорт", "тренер", "атлет", "футбол", "дзюдо", "плаван", "хоккей",
    ],
    "science": [
        "учён", "исследовател", "лаборант", "наука", "научн", "физик",
        "химик",
    ],
}

_MAX_RESOURCES_PER_CATEGORY = 5


def match_category(*texts: str) -> str | None:
    """Deterministic keyword match across all given text fields. Returns the
    category with the most keyword hits, or None if nothing matched — a silent
    miss is safer than attaching resources for the wrong field."""
    combined = " ".join(t for t in texts if t).lower()
    if not combined.strip():
        return None

    best_category: str | None = None
    best_score = 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        # Occurrence count, not just presence.
        score = sum(combined.count(kw) for kw in keywords)
        if score > best_score:
            best_score = score
            best_category = category
    return best_category


def resources_for_category(category: str | None) -> list[dict]:
    if category is None:
        return []
    catalog = tr("resource_catalog")["catalog"]
    return catalog.get(category, [])[:_MAX_RESOURCES_PER_CATEGORY]
