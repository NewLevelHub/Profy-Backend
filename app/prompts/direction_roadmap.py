"""Direction roadmap prompt + strict output schema.

The plan runs two tracks in parallel through every stage: `profile_track` deepens
the direction's core skill, `growth_track` attacks the student's weakest spot —
the one that would actually hold them back in this direction. From months_9 the
two converge into a single project.

Structured Outputs (strict mode) forbids minItems/maxItems, so "exactly 4 stages,
2-3 tasks per track" is asked for in the prompt and enforced by post-validation
in the caller (`_valid_stages`).
"""
import json

from app.models.direction import Direction
from app.schemas.roadmap import DIRECTION_HORIZONS
from app.schemas.student_context import StudentContext

CATEGORIES = [
    "knowledge", "skill", "practice", "project", "portfolio",
    "soft_skill", "subject", "community", "exam", "university",
]

_STAGE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["horizon", "title", "profile_track", "growth_track", "integration_project"],
    "properties": {
        "horizon": {"type": "string", "enum": DIRECTION_HORIZONS},
        "title": {"type": "string"},
        "profile_track": {
            "type": "object",
            "additionalProperties": False,
            "required": ["focus", "tasks"],
            "properties": {
                "focus": {"type": "string"},
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["text", "category", "priority"],
                        "properties": {
                            "text": {"type": "string"},
                            "category": {"type": "string", "enum": CATEGORIES},
                            "priority": {"type": "integer"},
                        },
                    },
                },
            },
        },
        "growth_track": {
            "type": "object",
            "additionalProperties": False,
            "required": ["focus", "tasks"],
            "properties": {
                "focus": {"type": "string"},
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["text", "category", "priority"],
                        "properties": {
                            "text": {"type": "string"},
                            "category": {"type": "string", "enum": CATEGORIES},
                            "priority": {"type": "integer"},
                        },
                    },
                },
            },
        },
        "integration_project": {"type": ["string", "null"]},
    },
}

DIRECTION_ROADMAP_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "target", "growth_focus", "stages",
        "skills_to_build", "subjects_to_focus", "university_track",
    ],
    "properties": {
        "target": {
            "type": "object",
            "additionalProperties": False,
            "required": ["role", "why", "horizon_years"],
            "properties": {
                "role": {"type": "string"},
                "why": {"type": "string"},
                "horizon_years": {"type": "integer"},
            },
        },
        "growth_focus": {
            "type": "object",
            "additionalProperties": False,
            "required": ["weakness", "why_it_matters"],
            "properties": {
                "weakness": {"type": "string"},
                "why_it_matters": {"type": "string"},
            },
        },
        "stages": {"type": "array", "items": _STAGE_SCHEMA},
        "skills_to_build": {"type": "array", "items": {"type": "string"}},
        "subjects_to_focus": {"type": "array", "items": {"type": "string"}},
        "university_track": {
            "type": "object",
            "additionalProperties": False,
            "required": ["specialties", "prepare"],
            "properties": {
                "specialties": {"type": "array", "items": {"type": "string"}},
                "prepare": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}

_SYSTEM_PROMPT = """\
Ты — сильный карьерный наставник для подростков. Ученик прошёл профтест, выбрал \
направление и подтвердил через ИИ-опрос, что оно ему подходит. Твоя задача — \
построить ЧЕСТНЫЙ, конкретный план развития именно в этом направлении.

Отвечай СТРОГО в JSON по заданной схеме, без текста вне JSON. Язык — русский, \
обращайся на «ты».

КОНЕЧНАЯ ЦЕЛЬ (target). Сначала определи, кем конкретно этот ученик может стать в \
этом направлении — не «специалистом в IT», а конкретной ролью (например, \
«backend-разработчик», «дата-аналитик», «репортёр-расследователь»). Выбирай роль \
под ЕГО сильные стороны, стиль мышления и то, что его мотивирует (values). В поле \
why объясни, почему именно эта роль ему подходит, ссылаясь на его данные. \
horizon_years — за сколько лет он реально может к ней прийти от своего возраста.

ТОЧКА РОСТА (growth_focus). Найди ОДНУ слабую сторону, которая будет реально мешать \
ему в этом направлении. Бери её из growth_areas (низкие баллы), subjects_hard, \
wellbeing_zones и особенно из inquiry.low_signals — утверждений, с которыми он не \
согласился. Пример: будущий журналист-интроверт — слабое место «общение с незнакомыми \
людьми». Будущий разработчик со слабой математикой — «алгебра». В why_it_matters \
объясни мягко и по делу, почему без этого он упрётся в потолок. Без осуждения.

ЭТАПЫ (stages) — ровно 4: months_3, months_6, months_9, months_12. В каждом два \
трека, которые идут ПАРАЛЛЕЛЬНО, по 2-3 задачи в каждом:
- profile_track — углубление в профильный навык направления;
- growth_track — прицельная работа над той самой точкой роста.
Логика этапов:
- months_3 — база и теория: профиль осваивает основы; рост закрывает пробел \
(курс, учебник, разбор темы). integration_project = null.
- months_6 — практика и выход из зоны комфорта: профиль делает первые \
практические задания; рост идёт туда, где слабый навык НУЖЕН вживую (кружок, \
секция, клуб, школьное сообщество). integration_project = null.
- months_9 — интеграция: оба трека ведут к ОДНОМУ проекту, где нужны сразу и \
профильный навык, и подтянутая слабая сторона. Опиши его в integration_project. \
Пример: взять интервью у трёх незнакомых людей — это и журналистика, и преодоление \
страха общения.
- months_12 — готовность к профильному пути: собрать результаты, честно оценить, \
насколько слабая сторона перестала мешать, выйти на профильные классы, олимпиады \
или конкурсы. Заполни integration_project, если проект уместен, иначе null.

ГЛУБИНА — СТРОГО ПО ВОЗРАСТУ (age, grade). Не давай общих советов «посмотри видео» \
там, где ученик уже может больше. 10-13 лет: кружки, простые проекты, книги, \
конкурсы, без профжаргона. 14-15 лет: он уже может углубляться по-настоящему — \
алгоритмы и олимпиадное программирование, разбор реальных кейсов, серьёзные \
учебники, первые самостоятельные проекты. 16-17 лет: профильная подготовка, \
олимпиады, стажировки, портфолио, подготовка к поступлению. Задачи должны быть \
посильны ЕМУ СЕЙЧАС и постепенно усложняться от этапа к этапу.

ВУЗ (university_track). Даже если цель ученика — не поступление, план обязан \
привести его к готовности поступить на близкую специальность: перечисли \
specialties (направления обучения) и prepare (что готовить: профильные предметы, \
экзамены, олимпиады, портфолио).

ЗАПРЕТ НА ВЫДУМКУ. У тебя НЕТ базы курсов, книг, кружков и школ. Никогда не \
выдумывай названия конкретных курсов, платформ, кружков, книг или организаций и не \
давай ссылок. Формулируй действие так, чтобы ученик сам нашёл: «найди в своём городе \
кружок робототехники», «пройди любой бесплатный онлайн-курс по основам Python», \
«разбери школьный учебник алгебры за 8 класс, тему квадратных уравнений». \
Конкретной должна быть ЗАДАЧА, а не бренд.

priority: 1 — самое важное в треке, дальше по возрастанию.\
"""


def _direction_brief(direction: Direction) -> dict:
    return {
        "name": direction.name,
        "description": direction.description,
        "professions": list(direction.professions or []),
        "skills_needed": list(direction.skills_needed or []),
        "subjects_to_develop": list(direction.subjects_to_develop or []),
    }


def build_messages(context: StudentContext, direction: Direction) -> list[dict[str, str]]:
    allowed = ", ".join(CATEGORIES)
    user_content = (
        f"НАПРАВЛЕНИЕ:\n{json.dumps(_direction_brief(direction), ensure_ascii=False, indent=2)}\n\n"
        f"УЧЕНИК (все, что мы о нём знаем):\n{context.model_dump_json(indent=2)}\n\n"
        f"Разрешённые значения category: {allowed}.\n\n"
        "Построй для этого ученика план развития в этом направлении по схеме."
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
