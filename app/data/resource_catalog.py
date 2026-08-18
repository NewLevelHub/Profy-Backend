"""Static, hand-verified resource catalogue for the roadmap's "Дополнительный
источник" block.

Every entry here was opened and checked by hand (title/topic actually matches,
link resolves, not a paywalled/dead/off-topic surprise) — see the product's
resource-research checklist for the full audit trail, including the links
that were dropped for being broken, mismatched, or too caveated to ship.

Deliberately NOT LLM-driven, same principle as Program.direction_slugs
tagging elsewhere in this product: with a small, static, hand-picked set of
links, a keyword match is both simpler and more auditable than asking a
model to pick one. `match_category` returns None (no resources attached)
rather than guessing when nothing scores — a wrong-topic link is worse than
no link, same reasoning the roadmap prompts use against inventing sources.
"""

RESOURCE_CATALOG: dict[str, list[dict]] = {
    "tech": [
        {"title": "«Поколение Python»", "kind": "курс", "url": "https://stepik.org/course/58852"},
        {"title": "Алгоритмы: теория и практика. Структуры данных", "kind": "курс", "url": "https://stepik.org/course/1547"},
        {"title": "Wokwi — симулятор Arduino/ESP32", "kind": "инструмент", "url": "https://wokwi.com"},
        {"title": "Tinkercad Circuits", "kind": "инструмент", "url": "https://www.tinkercad.com/circuits"},
        {"title": "E-Olymp — задачник по программированию", "kind": "задачник", "url": "https://www.eolymp.com/ru/"},
    ],
    "creative_design": [
        {"title": "Азбука Рисования", "kind": "видео", "url": "https://www.youtube.com/@AzbukaR"},
        {"title": "SketchUp для начинающих", "kind": "видео", "url": "https://www.youtube.com/watch?v=XJU9WBLsx_M"},
        {"title": "Behance — портфолио", "kind": "платформа", "url": "https://www.behance.net"},
        {"title": "Tilda Publishing", "kind": "инструмент", "url": "https://tilda.cc/ru/"},
    ],
    "medicine": [
        {"title": "Анатомия человека. ЕГЭ/ОГЭ по биологии", "kind": "курс", "url": "https://stepik.org/course/209034"},
        {"title": "PhET — химические симуляции", "kind": "инструмент", "url": "https://phet.colorado.edu/ru/simulations/filter?subjects=chemistry"},
        {"title": "«Химия вокруг нас»", "kind": "курс", "url": "https://www.lektorium.tv/chemistry"},
        {"title": "QazVolunteer.kz", "kind": "платформа", "url": "https://qazvolunteer.kz"},
        {"title": "Красный Полумесяц Казахстана — волонтёрство", "kind": "организация", "url": "https://redcrescent.kz/ru/volonterstvo"},
    ],
    "business": [
        {"title": "Fingramota.kz", "kind": "портал", "url": "https://fingramota.kz/ru/qarjy-quests/list"},
        {"title": "Business Model Canvas", "kind": "шаблон", "url": "https://miro.com/ru/templates/business-model-canvas/"},
        {"title": "Canvanizer", "kind": "инструмент", "url": "https://canvanizer.com"},
    ],
    "humanities": [
        {"title": "Журналистика и медиаграмотность", "kind": "курс", "url": "https://stepik.org/course/81"},
        {"title": "«Секреты хороших текстов»", "kind": "курс", "url": "https://stepik.org/course/59247"},
        {"title": "Психология саморазвития", "kind": "курс", "url": "https://stepik.org/course/71738"},
        {"title": "Общая психология (курс лекций МГУ)", "kind": "видео", "url": "https://www.youtube.com/playlist?list=PLt3fgqeygGTVk5khY228EBHujarUgyLfv"},
    ],
    "law": [
        {"title": "Әділет — база НПА Казахстана", "kind": "база данных", "url": "https://adilet.zan.kz"},
    ],
    "sport": [
        {"title": "Национальный Олимпийский Комитет РК", "kind": "организация", "url": "https://olympic.kz/ru"},
    ],
    "science": [
        {"title": "Республиканский центр «Дарын»", "kind": "организация", "url": "https://daryn.kz"},
        {"title": "CyberLeninka", "kind": "библиотека", "url": "https://cyberleninka.ru"},
        {"title": "Google Академия", "kind": "поиск", "url": "https://scholar.google.com"},
    ],
}

# Substring match, case-insensitive — deliberately simple and inspectable.
# Order inside a list doesn't matter; category with the most keyword hits wins.
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
    category with the most keyword hits, or None if nothing matched — a
    silent miss is safer than attaching resources for the wrong field."""
    combined = " ".join(t for t in texts if t).lower()
    if not combined.strip():
        return None

    best_category: str | None = None
    best_score = 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        # Occurrence count, not just presence — a direction whose text repeats
        # one category's keyword several times (e.g. "финанс..." showing up
        # in name + skills + subjects) should outweigh a single incidental
        # hit from another category's keyword elsewhere in the same text.
        score = sum(combined.count(kw) for kw in keywords)
        if score > best_score:
            best_score = score
            best_category = category
    return best_category


def resources_for_category(category: str | None) -> list[dict]:
    if category is None:
        return []
    return RESOURCE_CATALOG.get(category, [])[:_MAX_RESOURCES_PER_CATEGORY]
