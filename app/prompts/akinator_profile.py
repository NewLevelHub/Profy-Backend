"""Akinator leaf axis-profile prompt + strict output schema.

OFFLINE use only — see scripts/generate_profession_profiles.py. This module
drafts the `directions.profile` vector (see app/models/direction.py) for one
taxonomy leaf (profession) at a time: which of the 24 axes in app/core/axes.py
are significant for it, and their −2…+2 value. Always a draft — a human signs
off before it reaches the catalog (see the script's [GATE] AKN-009 note).
"""
import json

from app.core.axes import AXIS_CATALOG, AXIS_CODES, AxisFamily, is_valid_axis

_AXIS_VALUES: tuple[int, ...] = (-2, -1, 1, 2)

_AXIS_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["code", "value"],
    "properties": {
        "code": {"type": "string", "enum": sorted(AXIS_CODES)},
        # 0 is excluded on purpose: a zero axis is not significant and must be
        # omitted from the array rather than spelled out.
        "value": {"type": "integer", "enum": list(_AXIS_VALUES)},
    },
}

PROFILE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["axes"],
    "properties": {
        "axes": {"type": "array", "items": _AXIS_SCHEMA},
    },
}


def _axis_legend() -> str:
    lines = []
    for family in AxisFamily:
        axes = [a for a in AXIS_CATALOG if a.family == family]
        if axes:
            lines.append(f"{family.value}: " + ", ".join(f"{a.code}({a.label_ru})" for a in axes))
    return "\n".join(lines)


_SYSTEM_PROMPT = f"""\
Ты — методолог профориентационного теста-акинатора. Оцени ОДНУ профессию (лист \
дерева направлений) по 24 осям характера и деятельности.

ОСИ (код: смысл):
{_axis_legend()}

ПРАВИЛА:
- Диапазон каждой оси −2…+2. 0 значит «ось не значима для этой профессии» — такие \
оси в ответ не включай вообще (не пиши value: 0).
- Обычно значимы 6-14 осей из 24 — не старайся заполнить все подряд, только те, \
что реально отличают эту профессию.
- Используй только коды из списка выше, ничего не выдумывай и не сокращай.
- Знак — это полюс оси, не «сила»: например Obj-2 = разбирать/докапываться до сути, \
Obj+2 = строить/чинить инструмент; Focus-2 = многозадачность, Focus+2 = глубокий \
длительный фокус; Predict-2 = рутина и предсказуемость, Predict+2 = новизна и сюрпризы.
- Ставь ±2 там, где профессия действительно крайняя по оси — не бойся сильных \
значений. Это черновик: слабые «на всякий случай» веса по всем осям (только ±1) \
хуже, чем несколько уверенных ±2 — из-за них соседние профессии в одной категории \
перестают различаться при ревью.

Отвечай строго JSON по схеме, без текста вне JSON.\
"""


def build_messages(name: str, category: str | None = None) -> list[dict[str, str]]:
    user_lines = [f"Профессия: {name}"]
    if category:
        user_lines.append(f"Категория/соседи по дереву: {category}")
    user_lines.append("Оцени профиль по осям согласно схеме.")
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(user_lines)},
    ]


def build_retry_messages(
    messages: list[dict[str, str]], raw_response: dict, unknown_codes: list[str]
) -> list[dict[str, str]]:
    """Append a correction turn asking the model to drop/replace unknown axis codes."""
    correction = (
        f"Коды {unknown_codes} не входят в список допустимых осей и будут отброшены. "
        f"Используй только: {', '.join(sorted(AXIS_CODES))}. "
        "Верни исправленный список осей по той же схеме, без текста вне JSON."
    )
    return [
        *messages,
        {"role": "assistant", "content": json.dumps(raw_response, ensure_ascii=False)},
        {"role": "user", "content": correction},
    ]


def split_known_axes(data: dict) -> tuple[dict[str, int], list[str]]:
    """Split a raw model response into valid axis→value pairs and unknown codes.

    Defense in depth: the schema's enum already blocks unknown codes and zero
    values in strict mode, but a non-strict provider or a malformed response
    could still slip one through — callers use `unknown` to decide whether to
    re-ask the model (see scripts/generate_profession_profiles.py)."""
    known: dict[str, int] = {}
    unknown: list[str] = []
    for entry in data.get("axes", []):
        code = entry.get("code")
        value = entry.get("value")
        if is_valid_axis(code) and isinstance(value, int) and value != 0:
            known[code] = value
        else:
            unknown.append(code if code is not None else "?")
    return known, unknown
