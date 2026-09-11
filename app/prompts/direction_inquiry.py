"""Prompts + strict schemas for the direction-fit inquiry (questions + verdict)."""
import json

from app.models.direction import Direction
from app.prompts._locale import glossary_block, language_directive
from app.schemas.student_context import StudentContext

QUESTION_COUNT = 7
READINESS_LEVELS = ["Высокая готовность", "Средняя готовность", "Стоит присмотреться"]

# ─── Questions ──────────────────────────────────────────────────────────────

QUESTIONS_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["questions"],
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "kind"],
                "properties": {
                    "text": {"type": "string"},
                    "kind": {"type": "string", "enum": ["interest", "readiness"]},
                },
            },
        },
    },
}


def _questions_system(locale: str = "ru", direction_slug: str | None = None) -> str:
    glossary = glossary_block(locale, direction_slug=direction_slug)
    glossary_section = f"\n\n{glossary}" if glossary else ""
    return f"""\
Ты — тёплый карьерный наставник для подростков. По направлению и данным ученика \
составь ровно {QUESTION_COUNT} наводящих вопросов: они помогают ребёнку понять, \
подходит ли ему это направление и готов ли он в нём развиваться.

Микс: ~5 вопросов про интерес и склонности («нравится/интересно»), и 2 — МЯГКО про \
готовность к усилию: когда не получается с первого раза, самому искать решение, \
доводить проект до конца, переделывать ради качества. Формулируй ПОЗИТИВНО, без слов \
«рутина/скучно/часами».
Пример готовности: «Когда что-то не выходит сразу, мне интересно докопаться и починить».

Опирайся на интересы, кружки/секции (artifacts) и предметы ученика — вопросы должны \
быть про него. Тон по возрасту: middle — проще; senior — взрослее. Обращайся на «ты».
Каждый вопрос ребёнок оценивает по шкале «Совсем не про меня … Точно про меня», поэтому \
формулируй как утверждение. kind = interest | readiness. {language_directive(locale)} Строго JSON.{glossary_section}"""


# ─── Verdict ────────────────────────────────────────────────────────────────

VERDICT_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["fit_summary", "readiness", "note"],
    "properties": {
        "fit_summary": {"type": "string"},
        "readiness": {"type": "string", "enum": READINESS_LEVELS},
        "note": {"type": "string"},
    },
}


def _verdict_system(locale: str = "ru", direction_slug: str | None = None) -> str:
    glossary = glossary_block(locale, direction_slug=direction_slug)
    glossary_section = f"\n\n{glossary}" if glossary else ""
    return f"""\
Ты — тёплый наставник для подростков. На основе направления, данных ученика и его \
ответов на наводящие вопросы дай короткий вывод. Тон оптимистичный, поддерживающий, \
без давления. Обращайся на «ты».
fit_summary — 2-3 предложения: насколько направление тебе подходит, опираясь на твои \
ответы и интересы. readiness — одна из меток. note — 1 мягкий добрый совет, на что \
обратить внимание. {language_directive(locale)} Строго JSON.{glossary_section}"""


_QUESTIONS_SYSTEM = _questions_system("ru")
_VERDICT_SYSTEM = _verdict_system("ru")


def _direction_brief(direction: Direction) -> dict:
    return {
        "name": direction.name,
        "description": direction.description,
        "professions": list(direction.professions or []),
        "skills_needed": list(direction.skills_needed or []),
        "subjects_to_develop": list(direction.subjects_to_develop or []),
    }


def _student_brief(context: StudentContext) -> dict:
    return {
        "age": context.age,
        "age_group": context.age_group,
        "city": context.city,
        "subjects_liked": context.subjects_liked,
        "subjects_hard": context.subjects_hard,
        "clubs_sections": [a.value for a in context.artifacts],
        "riasec_code": "".join(context.code),
        "strengths": context.strengths,
        "riasec_profile": context.profile,
    }


def build_questions_messages(
    context: StudentContext, direction: Direction, *, locale: str | None = None
) -> list[dict[str, str]]:
    target_locale = locale or getattr(context, "locale", "ru")
    user = (
        f"НАПРАВЛЕНИЕ:\n{json.dumps(_direction_brief(direction), ensure_ascii=False)}\n\n"
        f"УЧЕНИК:\n{json.dumps(_student_brief(context), ensure_ascii=False)}\n\n"
        f"Составь {QUESTION_COUNT} наводящих вопросов по схеме."
    )
    return [
        {"role": "system", "content": _questions_system(target_locale, direction_slug=direction.slug)},
        {"role": "user", "content": user},
    ]


def build_verdict_messages(
    context: StudentContext, direction: Direction, qa: list[dict[str, str]], *, locale: str | None = None
) -> list[dict[str, str]]:
    target_locale = locale or getattr(context, "locale", "ru")
    user = (
        f"НАПРАВЛЕНИЕ:\n{json.dumps(_direction_brief(direction), ensure_ascii=False)}\n\n"
        f"УЧЕНИК:\n{json.dumps(_student_brief(context), ensure_ascii=False)}\n\n"
        f"ОТВЕТЫ УЧЕНИКА:\n{json.dumps(qa, ensure_ascii=False)}\n\n"
        "Дай короткий вывод по схеме."
    )
    return [
        {"role": "system", "content": _verdict_system(target_locale, direction_slug=direction.slug)},
        {"role": "user", "content": user},
    ]
