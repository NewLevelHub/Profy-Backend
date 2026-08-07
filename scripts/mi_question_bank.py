"""
MI (Multiple-Intelligences-style) question bank — junior's (6-9) replacement
for RIASEC. Junior is not career-oriented (TZ_Profi.md §4.1: "не
профориентация, а понять, что ребёнку интересно и что стоит попробовать"),
so this bank measures 8 broad interest/strength categories inspired by
Gardner's Multiple Intelligences instead of Holland codes.

Every item is entirely junior content (no middle/senior tier — Big Five
stays as junior's personality/thinking-style instrument, unchanged), so
every item carries `short_text`/`icon` for the forced-choice-pair UI
(TZ_Profi.md §13 bans Likert for junior) — there's no Likert-only subset
here the way RIASEC/Big Five have for middle/senior.

To change the question bank: edit this list and rerun
scripts/seed_mi_questions.py — nothing elsewhere hardcodes question count,
text, or per-category counts.
"""

QUESTIONS: list[dict] = [
    # verbal — слова и истории (6)
    {"mi_category": "verbal", "text": "Мне нравится узнавать новые слова и истории", "short_text": "Узнавать новые слова", "icon": "📚"},
    {"mi_category": "verbal", "text": "Мне нравится сочинять свои истории и сказки", "short_text": "Сочинять истории", "icon": "✏️"},
    {"mi_category": "verbal", "text": "Мне нравится читать книги", "short_text": "Читать книги", "icon": "📖"},
    {"mi_category": "verbal", "text": "Мне нравится рассказывать что-то интересное другим", "short_text": "Рассказывать другим", "icon": "🗣️"},
    {"mi_category": "verbal", "text": "Мне нравится разгадывать слова в кроссвордах", "short_text": "Разгадывать слова", "icon": "🔤"},
    {"mi_category": "verbal", "text": "Мне нравится учить новые языки и слова", "short_text": "Учить новые слова", "icon": "🌍"},

    # logical — логика и счёт (6)
    {"mi_category": "logical", "text": "Мне нравится решать задачки и головоломки", "short_text": "Решать головоломки", "icon": "🧩"},
    {"mi_category": "logical", "text": "Мне нравится считать в уме", "short_text": "Считать в уме", "icon": "🔢"},
    {"mi_category": "logical", "text": "Мне нравится играть в игры, где нужно думать по шагам", "short_text": "Играть в шахматы", "icon": "♟️"},
    {"mi_category": "logical", "text": "Мне нравится собирать конструктор по схеме", "short_text": "Собирать по схеме", "icon": "🧱"},
    {"mi_category": "logical", "text": "Мне нравится находить закономерности и правила", "short_text": "Находить правила", "icon": "🔍"},
    {"mi_category": "logical", "text": "Мне нравится раскладывать вещи по порядку и группам", "short_text": "Раскладывать по порядку", "icon": "📊"},

    # musical — музыка и ритм (6)
    {"mi_category": "musical", "text": "Мне нравится петь песни", "short_text": "Петь песни", "icon": "🎤"},
    {"mi_category": "musical", "text": "Мне нравится играть на музыкальном инструменте", "short_text": "Играть на инструменте", "icon": "🎹"},
    {"mi_category": "musical", "text": "Мне нравится танцевать под музыку", "short_text": "Танцевать под музыку", "icon": "💃"},
    {"mi_category": "musical", "text": "Мне нравится внимательно слушать красивую музыку", "short_text": "Слушать музыку", "icon": "🎧"},
    {"mi_category": "musical", "text": "Мне нравится придумывать свои мелодии", "short_text": "Придумывать мелодии", "icon": "🎼"},
    {"mi_category": "musical", "text": "Мне нравится хлопать и отбивать ритм", "short_text": "Отбивать ритм", "icon": "🥁"},

    # visual — картинки и образы (6)
    {"mi_category": "visual", "text": "Мне нравится рисовать", "short_text": "Рисовать", "icon": "🎨"},
    {"mi_category": "visual", "text": "Мне нравится собирать пазлы и картинки", "short_text": "Собирать пазлы", "icon": "🖼️"},
    {"mi_category": "visual", "text": "Мне нравится придумывать, как что-то будет выглядеть", "short_text": "Придумывать картинки", "icon": "💭"},
    {"mi_category": "visual", "text": "Мне нравится смотреть на карты и находить дорогу", "short_text": "Находить дорогу по карте", "icon": "🗺️"},
    {"mi_category": "visual", "text": "Мне нравится лепить из пластилина", "short_text": "Лепить из пластилина", "icon": "🖐️"},
    {"mi_category": "visual", "text": "Мне нравится запоминать, как что-то выглядело", "short_text": "Запоминать картинки", "icon": "👁️"},

    # bodily — движение и руки (6)
    {"mi_category": "bodily", "text": "Мне нравится бегать и играть в подвижные игры", "short_text": "Бегать и играть", "icon": "🏃"},
    {"mi_category": "bodily", "text": "Мне нравится заниматься спортом", "short_text": "Заниматься спортом", "icon": "⚽"},
    {"mi_category": "bodily", "text": "Мне нравится мастерить что-то своими руками", "short_text": "Мастерить руками", "icon": "🔨"},
    {"mi_category": "bodily", "text": "Мне нравится лазать и прыгать", "short_text": "Лазать и прыгать", "icon": "🤸"},
    {"mi_category": "bodily", "text": "Мне нравится собирать конструктор руками", "short_text": "Собирать руками", "icon": "🧰"},
    {"mi_category": "bodily", "text": "Мне нравится показывать, как что-то делать, а не рассказывать", "short_text": "Показывать руками", "icon": "👐"},

    # interpersonal — дружба и команда (6)
    {"mi_category": "interpersonal", "text": "Мне нравится играть с друзьями в команде", "short_text": "Играть в команде", "icon": "🤝"},
    {"mi_category": "interpersonal", "text": "Мне нравится помогать другим, когда у них что-то не получается", "short_text": "Помогать другим", "icon": "🤗"},
    {"mi_category": "interpersonal", "text": "Мне нравится знакомиться с новыми ребятами", "short_text": "Знакомиться с ребятами", "icon": "👋"},
    {"mi_category": "interpersonal", "text": "Мне нравится, когда меня слушают друзья", "short_text": "Дружить и общаться", "icon": "💬"},
    {"mi_category": "interpersonal", "text": "Мне нравится придумывать общие игры для всех", "short_text": "Придумывать игры для всех", "icon": "🎲"},
    {"mi_category": "interpersonal", "text": "Мне нравится делиться своими вещами с другими", "short_text": "Делиться с другими", "icon": "🎁"},

    # intrapersonal — своё мнение (6)
    {"mi_category": "intrapersonal", "text": "Мне нравится играть в одиночку в свои игры", "short_text": "Играть одному", "icon": "🧍"},
    {"mi_category": "intrapersonal", "text": "Мне нравится заниматься тем, что интересно именно мне", "short_text": "Заниматься своим", "icon": "🌙"},
    {"mi_category": "intrapersonal", "text": "Мне нравится делать что-то по-своему, а не как все", "short_text": "Делать по-своему", "icon": "⭐"},
    {"mi_category": "intrapersonal", "text": "Мне нравится сначала подумать самому, а потом действовать", "short_text": "Сначала подумать", "icon": "🤔"},
    {"mi_category": "intrapersonal", "text": "Мне нравится проводить время в тишине наедине с собой", "short_text": "Побыть одному", "icon": "🕊️"},
    {"mi_category": "intrapersonal", "text": "Мне нравится иметь своё мнение, даже если оно отличается от мнения друзей", "short_text": "Иметь своё мнение", "icon": "✋"},

    # naturalistic — природа и животные (6)
    {"mi_category": "naturalistic", "text": "Мне нравится наблюдать за животными", "short_text": "Наблюдать за животными", "icon": "🐾"},
    {"mi_category": "naturalistic", "text": "Мне нравится гулять на природе", "short_text": "Гулять на природе", "icon": "🌳"},
    {"mi_category": "naturalistic", "text": "Мне нравится ухаживать за растениями", "short_text": "Ухаживать за растениями", "icon": "🌱"},
    {"mi_category": "naturalistic", "text": "Мне нравится собирать камешки, листья и другие находки на улице", "short_text": "Собирать находки на улице", "icon": "🍂"},
    {"mi_category": "naturalistic", "text": "Мне нравится узнавать, как живут разные животные", "short_text": "Узнавать про животных", "icon": "🦁"},
    {"mi_category": "naturalistic", "text": "Мне нравится смотреть на облака, звёзды и небо", "short_text": "Смотреть на небо", "icon": "🌌"},
]

# order continues from the RIASEC + Big Five bank's combined sequence (never
# hardcoded — derived from their actual lengths, so the three banks never
# collide regardless of how any one of them changes size).
from scripts.bigfive_question_bank import QUESTIONS as _BIGFIVE_QUESTIONS  # noqa: E402
from scripts.riasec_question_bank import QUESTIONS as _RIASEC_QUESTIONS  # noqa: E402

_BASE = len(_RIASEC_QUESTIONS) + len(_BIGFIVE_QUESTIONS)
for _i, _q in enumerate(QUESTIONS, start=_BASE + 1):
    _q["order"] = _i
    _q["instrument"] = "mi"
    _q["age_tier"] = "junior"

assert len(QUESTIONS) == 48, f"expected 48 MI questions, got {len(QUESTIONS)}"
assert all(_q.get("short_text") and _q.get("icon") for _q in QUESTIONS), (
    "every MI item is junior-only and must carry short_text + icon"
)
