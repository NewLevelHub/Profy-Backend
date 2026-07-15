"""Akinator question generation prompt + strict output schema.

OFFLINE use only — see scripts/generate_questions.py. Axis, depth and kind
(direct/situational) are chosen by a human and passed in; this module only
drafts the natural-language content (question text, junior variant, answer
options with axis weights) for that fixed combination. The caller assembles
the full row and validates it against
app.schemas.akinator_question.AkinatorQuestionCreate.
"""

from app.core.axes import AXIS_CATALOG, AXIS_CODES

_AXIS_VALUES: tuple[int, ...] = (-2, -1, 1, 2)

_AXIS_WEIGHT_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["code", "value"],
    "properties": {
        "code": {"type": "string", "enum": sorted(AXIS_CODES)},
        # 0 is excluded on purpose: an axis with no real effect on this option
        # must be omitted from the array, not spelled out as value 0.
        "value": {"type": "integer", "enum": list(_AXIS_VALUES)},
    },
}

_OPTION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text", "axis_weights"],
    "properties": {
        "text": {"type": "string"},
        "axis_weights": {"type": "array", "items": _AXIS_WEIGHT_SCHEMA},
    },
}

QUESTION_CONTENT_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text", "text_junior", "options"],
    "properties": {
        "text": {"type": "string"},
        "text_junior": {"type": ["string", "null"]},
        "options": {"type": "array", "items": _OPTION_SCHEMA},
    },
}

_KIND_GUIDE: dict[str, str] = {
    "direct": (
        'ПРЯМОЙ вопрос: спрашивает о предпочтении напрямую и широко ("Что тебе '
        'интереснее?", "Что приятнее?"). Без сценария и ситуации.'
    ),
    "situational": (
        "СИТУАТИВНЫЙ вопрос: конкретная жизненная ситуация или дилемма, из которой "
        "предпочтение видно косвенно — прямой вопрос дал бы социально желательный "
        "ответ. Пример: «Ты почти доделал дело, всё работает. Замечаешь мелкую "
        "ошибку, которую вряд ли кто-то заметит. Времени в обрез.» с вариантами "
        "«переделаю» / «оставлю как есть» / «не знаю»."
    ),
}

_SYSTEM_PROMPT = """\
Ты пишешь вопросы для банка теста-акинатора по профориентации. Каждый вопрос \
опрашивает ОДНУ конкретную ось характера/деятельности из каталога 24 осей — \
семейство, глубина и формат вопроса тебе УЖЕ ЗАДАНЫ, менять их нельзя.

Отвечай СТРОГО в JSON по схеме, без текста вне JSON.

ПРАВИЛА:
- 2-4 варианта ответа. У КАЖДОГО варианта — свой вклад по осям (axis_weights): \
значения только -2/-1/1/2 (никогда 0 — если ось не задета, просто не добавляй её \
в список для этого варианта). Целевая ось обязана встретиться хотя бы в одном \
варианте. Можно дать вклад и по другим осям, если вариант реально их задевает.
- text_junior — упрощённая формулировка для младшего возраста (короче, без \
терминов, через понятный ребёнку пример); если вопрос и так простой для любого \
возраста — можно повторить text или оставить null.
- Не выдумывай варианты без смысла («и то и другое» допустим, но не как \
единственный вариант ответа).
- Язык — русский, обращение на «ты», подросток должен понять вопрос сразу, без \
терминологии.
"""


def build_messages(axis_code: str, depth: int, kind: str) -> list[dict[str, str]]:
    axis = next(a for a in AXIS_CATALOG if a.code == axis_code)
    guide = _KIND_GUIDE[kind]
    user_content = (
        f"Целевая ось: {axis.code} ({axis.label_ru}), семейство {axis.family.value}.\n"
        f"Глубина: {depth}.\n"
        f"Формат: {kind}. {guide}\n\n"
        "Напиши один вопрос под эту ось/глубину/формат по заданной схеме."
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
