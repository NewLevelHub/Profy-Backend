"""Deterministic RU/EN keyword -> program-category classifier.

Bridges specialty-group names from university-data/almaty_universities_data.py
and university-data/astana_universities_data.py to the same taxonomy used by
Program.direction_slug (see scripts/seed_universities.py).

Keyword matching only, no LLM — per the project's tagging policy, retagging
must stay deterministic and reviewable (see scripts/seed_kz_universities.py,
which prints every specialty it could not confidently classify so a human
can add a keyword or a manual override instead of silently guessing). That
"unresolved" list only catches names that matched NOTHING, though — it does
not catch names that matched something confidently WRONG. Use
scripts/_audit_keywords.py (not part of the seed pipeline, kept for future
review passes) to see every match for every keyword at once and eyeball it;
that is how "Клиническая психология" being claimed by medicine-pharmacy's
"клиническ", and "Аграрный AI" being claimed by biology-ecology's "аграрн"
before data-science-ai's own keyword ever got a chance, were both found —
neither ever showed up as "unresolved".

Keywords are regex patterns matched with re.search, not plain substrings —
short fragments silently match inside unrelated words otherwise (bare "art"
matched "Smart"/"Artificial", bare "искусств" matched "искусственный"
[artificial], bare "коммуникац" matched "телекоммуникации" [telecom
engineering]). Prefer whole-word forms, a negative lookahead, or a negative
lookbehind over adding another short fragment.

STYLE WORDS VS SUBJECT WORDS — the recurring failure mode in this file: a
"style" word like "инженер"/"engineering" or "промышленн" describes HOW a
field is taught, not WHAT it is, and appears identically across totally
unrelated professions (an airline pilot's "лётная эксплуатация", a
petroleum engineer's "нефтяная инженерия", and a software engineer's
"программная инженерия" all contain "engineering"-flavored words). A single
"engineering-science" bucket built on that word sent a food-production-
technologist match straight to helicopter piloting and oil exploration —
technically all "engineering", practically nothing alike. There is no
keyword fix for a style word, because it is working exactly as written; the
fix is to never key a category off one, and instead split by the SUBJECT
(construction, electrical power, oil/gas, aviation/transport, mechanical/
industrial, natural sciences, food/materials production) — each with its
own specific vocabulary that doesn't generalize across the others. Before
adding a new keyword anywhere, ask: does this word name a specific subject,
or could it equally describe five unrelated fields? If the latter, it
doesn't belong here regardless of how many real matches it would pick up.

categorize() classifies ONE atomic specialty name (e.g. "Дизайн интерьера"),
not a whole university department bundled into one string — see git history
for why an earlier group-level version (and even an earlier per-group vote)
both broke down on real source data.

Categories, in priority order (narrower/more specific domains are checked
before generic ones):
"""
import re

CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    (
        # Clinical/healthcare only. "клиническ" was removed — its only match
        # in the corpus was "Клиническая психология" (psychology-pedagogy),
        # not an actual clinical-medicine specialty; a keyword with zero
        # correct matches and one confidently wrong one is worse than none.
        "medicine-pharmacy",
        [
            "медицин(?!ская биология)", "медико", "врач", "стоматолог", "фармац",
            "здравоохран", "здоровь", "сестринск", "педиатр", "фельдшер",
            "medicine", "medical", "nursing", "nurse", r"health(?!tech)",
        ],
    ),
    (
        "biology-ecology",
        [
            "биолог", "медицинская биология", "ветеринар", "биотехнолог", "биофизик",
            # "экологи" alone also matched "Energy and Environmental
            # Engineering" / "Энергетическая и экологическая техника" — real
            # electrical/power-engineering specialties whose title happens to
            # mention "environmental" as a qualifier, not ecology programs.
            r"экологи(?!ческ\S*\s+(инженер|техник))",
            "окружающ", "природопользован", "животновод", "агроном",
            r"аграрн(?!\S*\s*ai\b)", "растени", "мелиораци", "аквакультур",
            "биоресурс", "охотовед", "зверовод", "почвовед", "biolog",
            "ecology", r"environment(?!al engineering)", r"естественн\S*\s+наук",
        ],
    ),
    (
        "sport-physical-education",
        ["физическ", "фитнес"],
    ),
    (
        "psychology-pedagogy",
        [
            "психолог", "педагог", "дошкольн", "начальн", "учитель", "преподават",
            "дефектолог", "воспитан", "psychology", "pedagog", "teacher",
            "литератур", "географ", "религиовед", "исламовед", "теолог",
            "истори", "социолог", "философ", "иностранн", "лингвист",
            "когнитивн", "preschool", "history", "sociolog", "philosoph",
            "anthropolog", "linguistic", "literature", r"\blanguage",
            r"социальн\S*\s+наук", r"социальн\S*\s+работ",
            "профессиональное обучение", "культурно-досугов", "библиотечн",
        ],
    ),
    (
        "law-public-administration",
        [
            "юрис", "юрид", "право", "таможен", "прокур", "следствен", "адвокат",
            "law", "правоохран", "государственное", "местное управление",
            "государственн и местн", "public administration",
            "регионовед", "востоковед", "тюрколог", "филолог", "перевод",
            "политолог", r"международн\S*\s+отношен",
            "political science", "translation", "international relations",
        ],
    ),
    (
        "finance-economics",
        [
            "финанс", "эконом", "банков", "бухгалт", "аудит", "налог",
            "страхован", "finance", "econom", "accounting", "actuar",
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
            "журналист", "медиа", "реклам", r"связ[ьи] с общественностью", "pr-",
            "маркетинг", "journalism", "media", "marketing",
            r"(?<!теле)коммуникац",
        ],
    ),
    (
        "design-digital-art",
        [
            "дизайн", r"искусств(?!енн)", "живопис", "скульптур", "хореограф",
            "режиссур", r"\bактер", "музык", "вокал", "консерватор", "кино",
            "анимаци", "фотограф", "оператор", "сценограф", "декоративн",
            "балет", "танц", "исполнительств", "fashion", "технология моды",
            "дирижир", "композици", "аудио", "design", "fine art", "film",
        ],
    ),
    (
        "data-science-ai",
        [
            # Stems, not full phrases — Russian case endings ("науки о
            # данных" vs "наука о данных") mean an exact phrase match misses
            # most real occurrences.
            "data science", r"наук[аи] о данн", "искусственн", "статистик",
            "machine learning", "big data", "нейросет", "artificial intelligence",
            "data analysis", "аналитика big data", "statistics",
            # Exact known QAIRU track names — safer than a bare "ai" keyword,
            # which would match almost anything (see "Smart"/"Artificial"
            # note above).
            "physical ai", "govtech ai", "fintech ai", "healthtech ai",
            "аграрный ai", "промышленный ai",
        ],
    ),
    (
        "it-development",
        [
            # "программ" alone also matches generic "образовательных программ"
            # (academic programs) — require a software-specific suffix
            # (программНое/программНая, программИРОВАние, программИСТ).
            r"программ(?=н|ирова|ист)", "software", "вычислительн", "информац",
            "информатик", r"it[ -]",
            "кибербезопасн", r"кибер\s?безопасн", "cybersecurity",
            "сети и", "сетев", "телекоммуникац", "телематик", "internet", "smart",
            "computing", "компьютерн", "computer", r"\bcs\b", "digital technolog",
            "криптолог", "цифров",
        ],
    ),
    (
        # Materials/production engineering — food, textile, chemical
        # processing. Deliberately separate from mechanical/industrial:
        # these are about WHAT is produced (food, fabric), not the machinery
        # discipline. Checked before natural-sciences-research so "химическая
        # технология" (applied) doesn't fall through to bare "хими" there.
        "production-technology",
        [
            "пищев", "продовольств", "перерабатыва", "нанотехнолог", "текстил",
            "лёгк", "легк", "химическая технология", "chemical", "materials",
            "стандартизац", "метролог", "сертификац",
        ],
    ),
    (
        "construction-architecture",
        [
            "строител", "архитектур", "architecture", "civil",
            "зданий", "сооружени", "снабжен", "проектирован", "вентиляц",
            "мостов", "тоннел", "градостроительств",
        ],
    ),
    (
        # Machinery, automation, robotics, general industrial engineering —
        # distinct from construction/electrical/oil-gas, which have their
        # own specific vocabularies below.
        "mechanical-industrial-engineering",
        [
            "машиностроен", "механическ", "мехатрон", "робототех", "robotics",
            "приборостроен", "автоматизац", "промышленная инженерия", "mechanical",
            "industrial engineering",
            "process engineering", r"оборудован(?![а-я\s]*аэропорт)", "биомедицинск",
            "жизнедеятельност",
        ],
    ),
    (
        "electrical-power-engineering",
        [
            "электротехн", "энергет", "энерго", "электрическ", "electrical",
            "electronic", "power engineering", "energy engineering", "радиотехн",
        ],
    ),
    (
        "oil-gas-mining-geology",
        [
            "нефт", "горн", "геолог", "уран", "радиоактивн",
            "petroleum", "mining", "geology",
        ],
    ),
    (
        "transport-aviation-engineering",
        [
            "транспорт", "авиац", "аэропорт", "авиони", "летательн",
            # A digit-hyphen prefix ("6-летняя программа") is a year count,
            # not "лётный" (flight) — excluded so it doesn't collide with
            # e.g. a 6-year medical program.
            r"(?<!\d-)л[её]тн", "аэронавигацион", "полет", "дрон", "автономн",
            "судов", "дорожн", "локомотив", "подвижного состава",
        ],
    ),
    (
        "natural-sciences-research",
        [
            "математи", "физика", "хими", "археолог", "метеоролог", "сейсмолог",
            "mathematic", "physics", "chemistry",
        ],
    ),
]

DEFAULT_CATEGORY = "business-management"


def categorize(specialty_name: str) -> tuple[str, bool]:
    """Returns (category_slug, was_confident).

    was_confident is False when nothing matched — callers should log these
    for manual review instead of silently trusting DEFAULT_CATEGORY.
    """
    text = specialty_name.lower()
    for category, patterns in CATEGORY_KEYWORDS:
        if any(re.search(pattern, text) for pattern in patterns):
            return category, True
    return DEFAULT_CATEGORY, False
