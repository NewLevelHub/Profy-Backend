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
    "interest": "заниматься тем, что по-настоящему интересно",
    "challenge": "решать сложные задачи и расти",
    "helping": "приносить пользу другим",
    "freedom": "самому принимать решения",
    "money": "получать хороший материальный результат",
    "recognition": "быть признанным экспертом",
    "stability": "иметь стабильность и предсказуемость",
    "creation": "создавать что-то своё",
    "teamwork": "работать в сильной команде",
}


def highlight_phrases(top: list[str]) -> list[str]:
    return [f"Тебя больше всего драйвит — {_DRIVER_PHRASES[c]}" for c in top if c in _DRIVER_PHRASES]
