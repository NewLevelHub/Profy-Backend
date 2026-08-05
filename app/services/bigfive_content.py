"""
Big Five methodology reference tables — mirrors riasec_content.py's role.
"""

# Russian domain labels — admin/debug use only. Raw Big Five percentages are
# never shown to the student directly (TZ_Profi.md §18.3: numbers are
# admin-only); the student-facing report uses thinking_style + the
# interpreted phrases below instead.
BIGFIVE_LABELS: dict[str, str] = {
    "N": "Эмоциональная чувствительность",
    "E": "Экстраверсия",
    "O": "Открытость опыту",
    "A": "Доброжелательность",
    "C": "Добросовестность",
}

# The fixed 1-5 scale every Big Five question is answered on — different
# wording from RIASEC's LIKERT_LABELS (agreement, not liking), needed for
# admin-panel display of raw answers.
LIKERT_LABELS: list[str] = [
    "Очень Неточно",
    "Умеренно Неточно",
    "Ни Точно, Ни Неточно",
    "Умеренно Точно",
    "Очень Точно",
]

THINKING_STYLE_LABELS: dict[str, str] = {
    "creative_think": "Генерация нестандартных решений",
    "systematic": "Выстраивание систем и порядка",
    "strategic": "Видение целого, планирование наперёд",
    "practical": "Доведение идеи до работающего результата",
}

# Only 3 domains feed "Сильные стороны" (Openness, Conscientiousness, low
# Neuroticism) — confirmed with product owner: Extraversion/Agreeableness
# aren't reliably "strengths" (can be a liability depending on context), so
# they're excluded here rather than guessed at.
_STRONG = 60.0
_LOW = 40.0


def strength_phrases(bigfive_normalized: dict[str, float]) -> list[str]:
    phrases: list[str] = []
    if bigfive_normalized.get("O", 0.0) >= _STRONG:
        phrases.append("Тебе интересно пробовать новое и нестандартно смотреть на вещи")
    if bigfive_normalized.get("C", 0.0) >= _STRONG:
        phrases.append("Ты умеешь довести начатое до конца, даже когда это скучно")
    if bigfive_normalized.get("N", 100.0) <= _LOW:
        phrases.append("Ты спокойно переживаешь неудачи и пробуешь снова")
    return phrases
