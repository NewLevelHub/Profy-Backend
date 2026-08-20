"""
RIASEC methodology reference tables — fixed by the model itself (6 types),
not "question bank" content. Kept as constants, not DB rows: unlike the
question/direction catalogs these don't need independent swapping, and a
6-key dict is small enough that a table would be over-engineering.
"""

# Russian labels — used server-side for interest_map/career content
# (report_v2_assembler.py) and RIASEC evidence text (report_narrative_context.py).
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

# Short, human strength-observation sentence per Holland type — richer than
# RIASEC_LABELS' bare type name (e.g. "Реалистичный"). Used as the evidence
# text for interest items feeding fallback strength cards
# (report_narrative_context.py); interest_map (all 6 spheres, not just the
# vetted top ones) uses the bare RIASEC_LABELS name instead.
RIASEC_STRENGTH_PHRASES: dict[str, str] = {
    "R": "Любишь работать руками и доводить дело до реального результата",
    "I": "Любишь докапываться до сути и разбираться, как всё устроено",
    "A": "Легко придумываешь идеи и нестандартные решения",
    "S": "Хорошо понимаешь людей и замечаешь, кому нужна помощь",
    "E": "Умеешь брать инициативу и вести за собой",
    "C": "Умеешь наводить порядок и доводить дело до конца",
}

# Deterministic fallback "why" for a matched career/direction when no
# specific evidence overlaps its Holland code — never leaves `why` empty
# (TZ_Profi.md §18.2: every shown direction needs an explanation). Named
# honestly rather than papering over the gap: this direction was ranked by
# the interest test's overall pattern, not by a specific evidenced strength
# the student can point to — saying so plainly reads more trustworthy than
# a vague "matches what you've shown" that implies a specific link that
# doesn't actually exist (result-quality-fixes.md §3, variant A).
#
# A flat/undifferentiated profile can legitimately land 5-10 of the 10 shown
# careers in this fallback (riasec_service.strengths_weaknesses' 70.0 bar
# often clears zero letters) — a single string then repeated verbatim across
# unrelated careers read as broken/copy-pasted. Several honest rephrasings
# of the same disclosure let report_v2_assembler cycle through them instead
# of repeating one sentence (result-quality-fixes.md §3 follow-up, found live
# 2026-08-19: 10/10 identical "why" for a flat profile).
NEUTRAL_CAREER_WHY_VARIANTS: list[str] = [
    (
        "Это направление подобрано по общей картине теста интересов, а не по "
        "одной конкретной сильной стороне — иногда так тоже бывает, и это "
        "нормально: стоит попробовать и посмотреть, откликается ли."
    ),
    (
        "Здесь нет одной ярко выраженной черты, на которую можно сослаться — "
        "направление всплыло из общего сочетания твоих ответов. Понять, "
        "откликается ли оно, можно только попробовав."
    ),
    (
        "Прямого совпадения с твоими сильными сторонами тест не показал — "
        "направление ближе по общему балансу интересов, чем по одной "
        "конкретной черте. Не повод отказываться сразу, повод присмотреться."
    ),
    (
        "Тест не выделил здесь конкретную сильную сторону, но направление "
        "всё равно попало в подборку по совокупности ответов — иногда стоит "
        "довериться и такому сигналу."
    ),
    (
        "Однозначного совпадения с твоими сильными сторонами нет — "
        "направление в списке благодаря общей картине теста, а не отдельному "
        "яркому качеству. Проверить, откликается ли оно, можно только на практике."
    ),
]

# Back-compat alias — some callers/tests only need "a" neutral fallback
# string, not the rotation (e.g. to assert a career.why is *some* neutral
# variant). Always the first, most-established phrasing.
NEUTRAL_CAREER_WHY = NEUTRAL_CAREER_WHY_VARIANTS[0]

# Same idea for `try_now` (StudentCareer.try_now, app/schemas/result_v2.py):
# a Direction row with no first_steps in the DB must never leave the field
# empty — try_now is a required, always-non-empty part of the schema.
NEUTRAL_TRY_NOW = "Понаблюдай, как выглядит эта сфера на практике, и попробуй похожую маленькую задачу."

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
