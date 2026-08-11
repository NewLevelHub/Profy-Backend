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
                            "required": ["text", "description", "category", "priority"],
                            "properties": {
                                "text": {"type": "string"},
                                "description": {"type": "string"},
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
понятный заголовок (title) и 3 задачи (tasks). У каждой задачи: text (короткое \
название — что конкретно сделать), description, category (из разрешённого \
списка), priority (1 — самое важное, дальше по возрастанию).

description — раскрывает задачу коротко, но не одним общим предложением. Каждое \
предложение обязано либо (а) сказать, с чего конкретно начать, либо (б) объяснить, \
почему это подходит именно ЭТОМУ ученику со ссылкой на конкретный сигнал из его \
данных, либо (в) дать понятный признак «готово». Обычно достаточно 1-3 предложений \
— задачи goal-роадмапа короче и раньше по горизонту, чем этапы направления, не \
нужно тянуть их искусственно длиннее. Запрещены общие фразы без конкретики («это \
полезный навык», «попробуй разное») — если предложение не делает (а)/(б)/(в), не \
пиши его.

Тон и сложность — строго по возрасту (age_group):
- junior и middle: простой, тёплый язык, обращение на «ты». БЕЗ терминов и \
жаргона (ML, AI, DevOps, SQL, backend и т.п.). Конкретные, посильные ребёнку \
занятия: кружки, книги, простые проекты, наблюдения, игры, поездки.
- senior: можно профессиональные термины, онлайн-курсы, олимпиады, стажировки, \
а при цели поступления — университеты, экзамены и документы.

Персонализация: опирайся на RIASEC-код ученика (code), сильные и слабые \
стороны (strengths/weaknesses), любимые и сложные предметы (subjects_*) \
и подобранные направления (careers). План должен вести к его цели.

Дополнительно, но НЕ в каждой задаче и НЕ механически: в паре мест, где это реально \
объясняет выбор, можно опереться на personality_notes (стиль работы) и \
motivation_top/motivation_highlights (что его драйвит) — например, в description \
задачи или в обосновании, почему именно такой первый шаг подходит. Используй, \
только если черта или мотив реально относятся к конкретной задаче — не вставляй их \
«для полноты» в план, где RIASEC и так всё объясняет. Никогда не цитируй числа \
(ни проценты RIASEC, ни баллы личности) — только сам тип/черту словами. И никогда \
не наклеивай ярлык типа личности («ты интроверт», «у тебя высокий N») — пересказывай \
personality_notes своими словами, через поведение и предпочтения, как они уже \
сформулированы там.

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
