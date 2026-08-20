"""
Motivation methodology reference tables — mirrors bigfive_content.py's role.
"""

# Admin/debug use only — raw per-category scores are never shown to the
# student (same TZ_Profi.md §18.3 principle as RIASEC/Big Five numbers).
MOTIVATION_LABELS: dict[str, str] = {
    "interest": "Интерес к делу",
    "challenge": "Вызов и рост",
    "helping": "Польза другим",
    "freedom": "Свобода решений",
    "money": "Материальный результат",
    "recognition": "Признание",
    "stability": "Стабильность",
    "creation": "Создавать своё",
    "teamwork": "Команда",
}

_DRIVER_PHRASES: dict[str, str] = {
    "interest": "Заниматься тем, что по-настоящему интересно",
    "challenge": "Решать сложные задачи и расти",
    "helping": "Приносить пользу другим",
    "freedom": "Самому принимать решения",
    "money": "Получать хороший материальный результат",
    "recognition": "Быть признанным экспертом",
    "stability": "Иметь стабильность и предсказуемость",
    "creation": "Создавать что-то своё",
    "teamwork": "Работать в сильной команде",
}


def highlight_phrases(top: list[str]) -> list[str]:
    # No shared lead-in ("Тебя больше всего драйвит — ") repeated per item —
    # with 2-3 top categories that read as the same sentence stuttering 2-3
    # times. The "what this list is" framing belongs once, at the section
    # level (frontend heading), not per phrase.
    return [_DRIVER_PHRASES[c] for c in top if c in _DRIVER_PHRASES]
