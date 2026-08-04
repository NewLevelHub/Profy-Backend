"""
RIASEC methodology reference tables — fixed by the model itself (6 types),
not "question bank" content. Kept as constants, not DB rows: unlike the
question/direction catalogs these don't need independent swapping, and a
6-key dict is small enough that a table would be over-engineering.
"""

# Russian labels — used server-side for the LLM summary prompt (report_summary.py).
# The frontend keeps its own copy for UI (RIASEC_LABELS in shared/config/constants.ts) —
# two small, independent consumers of the same fixed methodology table, not duplicated data.
RIASEC_LABELS: dict[str, str] = {
    "R": "Реалистичный",
    "I": "Исследовательский",
    "A": "Артистичный",
    "S": "Социальный",
    "E": "Предприимчивый",
    "C": "Конвенциональный",
}

# The fixed 1-5 scale every RIASEC question is answered on. Also reused by the
# direction-fit inquiry feature (its own, separate small Likert-scale questions).
LIKERT_LABELS: list[str] = [
    "Очень не нравится",
    "Скорее не нравится",
    "Нейтрально",
    "Скорее нравится",
    "Очень нравится",
]

# Methodology §5.4 — extracurricular activities per type, used to build both
# `reinforce` (for the student's top code) and `compensate` (for a weak type
# that's relevant to their interests) in the development plan.
TYPE_ACTIVITIES: dict[str, list[str]] = {
    "R": ["спортивные секции", "техническое творчество", "робототехника", "авиамоделирование", "туризм и выживание"],
    "I": ["научные кружки", "олимпиады по точным наукам", "исследовательские проекты", "шахматы"],
    "A": ["студия рисования", "музыкальная студия", "театральная студия", "кружок литературного творчества", "фото/видео"],
    "S": ["волонтёрство", "вожатство", "дебат-клубы", "наставничество", "кружок психологии"],
    "E": ["бизнес-клуб", "ученическое самоуправление", "стартап-акселератор", "ораторское искусство"],
    "C": ["кружок по работе с данными и Excel", "бухгалтерский учёт для школьников", "организационные роли в мероприятиях"],
}
