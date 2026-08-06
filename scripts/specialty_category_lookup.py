"""Deterministic RU/EN keyword -> program-category classifier.

Bridges specialty-group names from university-data/almaty_universities_data.py
and university-data/astana_universities_data.py to the same ~12-category
taxonomy used by Program.direction_slug (see scripts/seed_universities.py).
Grew from an original 10 after medicine-biology-ecology and sport/PE proved
too coarse in practice (see git history for the concrete before/after).

Keyword matching only, no LLM — per the project's tagging policy, retagging
must stay deterministic and reviewable (see scripts/seed_kz_universities.py,
which prints every group it could not confidently classify so a human can
add a keyword or a manual override instead of silently guessing).

Keywords are regex patterns matched with re.search, not plain substrings —
short fragments silently match inside unrelated words otherwise (bare "art"
matched "Smart"/"Artificial", bare "искусств" matched "искусственный"
[artificial], both of which sent IT/AI specialty groups into
design-digital-art). Prefer whole-word forms or a negative lookahead over
adding another short fragment.

Categories, in priority order (narrower/more specific domains are checked
before generic ones so e.g. "медицинская биология" doesn't fall through to
engineering-science on the word "биология" -> "инженер" overlap):
"""
import re

CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    (
        # Clinical/healthcare only — kept separate from biology-ecology so a
        # pharmacist/doctor match doesn't surface pure ecology or animal-
        # science programs, and from sport-physical-education so it doesn't
        # surface PE-coach training either (both bit a shared bucket before
        # and produced irrelevant results for e.g. "Фармацевт").
        "medicine-pharmacy",
        [
            "медицин", "врач", "стоматолог", "фармац", "здравоохран",
            "сестринск", "педиатр", "фельдшер", "клиническ", "medicine",
            "medical", "nursing", "nurse", r"health(?!tech)",
        ],
    ),
    (
        "biology-ecology",
        [
            "биолог", "ветеринар", "биотехнолог", "биофизик", "экологи",
            "окружающ", "природопользован", "животновод", "агроном", "biology",
        ],
    ),
    (
        "sport-physical-education",
        ["физическ"],
    ),
    (
        "psychology-pedagogy",
        [
            "психолог", "педагог", "дошкольн", "начальн", "учитель", "преподават",
            "дефектолог", "воспитан", "psychology", "pedagog", "teacher",
            "литератур", "географ", "религиовед", "исламовед",
        ],
    ),
    (
        "law-public-administration",
        [
            "юрис", "юрид", "право", "таможен", "прокур", "следствен", "адвокат",
            "law", "правоохран", "государственное", "местное управление",
            "государственн и местн", "public administration",
            "регионовед", "востоковед", "тюрколог", "филолог",
        ],
    ),
    (
        "finance-economics",
        [
            "финанс", "экономик", "банков", "бухгалт", "аудит", "налог",
            "страхован", "finance", "economics", "accounting", "actuar",
        ],
    ),
    (
        "business-management",
        [
            "менеджмент", "бизнес", "предпринимат", "логистик", "туризм",
            "гостепри", "гостинич", "ресторанн", "management", "business",
            "logistics", "tourism", "hospitality", "администрирован",
        ],
    ),
    (
        "media-marketing",
        [
            "журналист", "медиа", "реклам", "связи с общественностью", "pr-",
            "маркетинг", "journalism", "media", "marketing", "коммуникац",
        ],
    ),
    (
        "design-digital-art",
        [
            "дизайн", r"искусств(?!енн)", "живопис", "скульптур", "хореограф",
            "режиссур", r"\bактер", "музык", "вокал", "консерватор", "кино",
            "анимаци", "фотограф", "оператор", "сценограф", "декоративн",
            "балет", "танц", "исполнительств", "design", "fine art", "film",
        ],
    ),
    (
        "data-science-ai",
        [
            # Stems, not full phrases — Russian case endings ("науки о
            # данных" vs "наука о данных", "искусственного интеллекта" vs
            # "искусственный интеллект") mean an exact phrase match misses
            # most real occurrences.
            "data science", r"наук[аи] о данн", "искусственн",
            "machine learning", "big data", "нейросет", "artificial intelligence",
            "data analysis", "аналитика big data",
        ],
    ),
    (
        "engineering-science",
        [
            "инженер", "строительств", "архитектур", "физика", "математика",
            "химия", "геолог", "нефт", "горн", "машиностроен", "энергетик",
            "электротехн", "робототех", "приборостроен", "engineering",
            "architecture", "physics", "mathematics", "chemistry", "mining",
            "petroleum", "земельн", "сельск", "агротехник",
            "пищев", "лёгк", "промышленн", "авиац", "лётн",
        ],
    ),
    (
        "it-development",
        [
            "программ", "software", "вычислительн", "информацион", "it ",
            "кибербезопасн", "cybersecurity", "сети и", "телекоммуникац",
            "компьютерн", "computer", "cs ", "digital technolog",
        ],
    ),
]

DEFAULT_CATEGORY = "business-management"


def categorize(group_name: str, program_names: list[str]) -> tuple[str, bool]:
    """Returns (category_slug, was_confident).

    was_confident is False when nothing matched and DEFAULT_CATEGORY was used
    as a fallback — callers should log these for manual review.
    """
    text = (group_name + " " + " ".join(program_names)).lower()
    for category, patterns in CATEGORY_KEYWORDS:
        if any(re.search(pattern, text) for pattern in patterns):
            return category, True
    return DEFAULT_CATEGORY, False
