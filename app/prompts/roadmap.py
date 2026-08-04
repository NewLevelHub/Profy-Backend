"""Roadmap generation prompt + strict output schema for the LLM.

The JSON schema mirrors the RoadmapResponse/RoadmapMilestone/RoadmapTask
Pydantic models so the model's output parses straight into them. Structured
Outputs (strict mode) forbids minItems/maxItems, so "exactly 5 horizons / 3
tasks" is asked for in the prompt and enforced by post-validation in the caller.
"""
from app.schemas.student_context import StudentContext

HORIZONS = ["month_1", "months_3", "months_6", "year_1", "until_goal"]

CATEGORIES = [
    "explore", "planning", "knowledge", "skill", "practice", "portfolio",
    "career", "education", "requirement", "exam", "documents", "application",
    "finance", "admission",
]

# Strict JSON schema for OpenAI Structured Outputs (matches RoadmapMilestone/Task).
ROADMAP_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["milestones"],
    "properties": {
        "milestones": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["horizon", "title", "tasks"],
                "properties": {
                    "horizon": {"type": "string", "enum": HORIZONS},
                    "title": {"type": "string"},
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
        },
    },
}

_GOAL_FRAMING = {
    "explore": "Ученик хочет понять себя. Помоги ему исследовать интересы и попробовать разное, без давления с выбором.",
    "unsure": "Ученик пока не определился. Помоги мягко присмотреться к разным сферам и почувствовать, что нравится.",
    "profession": "Ученик выбирает профессию. Веди его к конкретному направлению: навыки, практика, первый опыт, портфолио.",
    "university": "Ученик готовится к поступлению. Веди к цели: закрыть требования, документы, экзамены, подача заявки.",
}

_SYSTEM_PROMPT = """\
Ты — тёплый и внимательный карьерный наставник для детей и подростков. Ты \
составляешь персональный план развития (роадмап) по результатам \
профориентационного теста.

Отвечай СТРОГО в JSON по заданной схеме, без текста вне JSON.

Структура плана: ровно 5 этапов (milestones) — по одному на каждый горизонт: \
month_1, months_3, months_6, year_1, until_goal. У каждого этапа: короткий \
понятный заголовок (title) и 3 задачи (tasks). У каждой задачи: text (что \
конкретно сделать), category (из разрешённого списка), priority (1 — самое \
важное, дальше по возрастанию).

Тон и сложность — строго по возрасту (age_group):
- junior и middle: простой, тёплый язык, обращение на «ты». БЕЗ терминов и \
жаргона (ML, AI, DevOps, SQL, backend и т.п.). Конкретные, посильные ребёнку \
занятия: кружки, книги, простые проекты, наблюдения, игры, поездки.
- senior: можно профессиональные термины, онлайн-курсы, олимпиады, стажировки, \
а при цели поступления — университеты, экзамены и документы.

Персонализация: опирайся на RIASEC-код ученика (code), сильные и слабые \
стороны (strengths/weaknesses), любимые и сложные предметы (subjects_*) \
и подобранные направления (careers). План должен вести к его цели.

Локальные возможности: используй город (city) и страну (country), чтобы \
предлагать реальные местные варианты — кружки, школы, бесплатные программы, \
олимпиады. Если не уверен, что конкретное место существует, формулируй мягко \
(«узнай о…», «поищи в своём городе…») и не выдавай выдуманное за факт.

Язык ответа — русский.\
"""


def build_messages(context: StudentContext) -> list[dict[str, str]]:
    framing = _GOAL_FRAMING.get(context.goal, _GOAL_FRAMING["explore"])
    allowed = ", ".join(CATEGORIES)
    user_content = (
        f"{framing}\n\n"
        f"Разрешённые значения category: {allowed}.\n\n"
        f"Данные ученика (JSON):\n{context.model_dump_json(indent=2)}\n\n"
        "Составь для этого ученика персональный роадмап по схеме."
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
