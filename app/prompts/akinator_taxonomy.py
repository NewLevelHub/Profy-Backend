"""Akinator taxonomy expansion prompt + strict output schema.

OFFLINE use only — see scripts/generate_taxonomy.py. This module produces the
messages/schema for proposing new tree nodes (professions or intermediate
categories) beyond the starting ~67-profession catalog. It only proposes
skeleton structure (slug/name/parent/is_leaf); axis profile weights and
age-facing labels are filled in by a human afterwards, not generated here.
"""

_NODE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["slug", "name", "parent_slug", "is_leaf"],
    "properties": {
        "slug": {"type": "string"},
        "name": {"type": "string"},
        "parent_slug": {"type": ["string", "null"]},
        "is_leaf": {"type": "boolean"},
    },
}

AKINATOR_TAXONOMY_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["nodes"],
    "properties": {
        "nodes": {"type": "array", "items": _NODE_SCHEMA},
    },
}

_SYSTEM_PROMPT = """\
Ты помогаешь расширять офлайн-каталог дерева профессий для профориентационного \
теста-акинатора. Дерево идёт от общего к частному: наверху широкие направления \
(is_leaf=false), внизу — конкретные профессии, которыми дерево заканчивается \
(is_leaf=true).

Отвечай СТРОГО в JSON по схеме, без текста вне JSON.

ПРАВИЛА:
- slug — латиницей, kebab-case, короткий (например "backend-developer"), \
уникальный во всём каталоге (и старом, и новом).
- name — название на русском, понятное подростку.
- parent_slug — slug родителя. Либо это slug из УЖЕ СУЩЕСТВУЮЩЕГО каталога \
(узел пристраивается к текущему дереву), либо slug другого узла ИЗ ЭТОГО ЖЕ \
ответа (тогда в списке сначала должен идти родитель, потом его дети) — так можно \
предложить сразу несколько уровней глубины за один раз. У корневых узлов \
parent_slug = null.
- is_leaf — true ТОЛЬКО для конкретной профессии/должности — того, кем человек \
РАБОТАЕТ (например "Скульптор", "Композитор", "Хирург-ортопед"). false — для \
промежуточной категории/направления/темы интереса, у которой будут дочерние узлы.
- ЧАСТАЯ ОШИБКА: лист = название дисциплины, жанра или предмета интереса \
("Живопись", "Классическая музыка", "Хирургия") вместо профессии. Если сомневаешься, \
задай вопрос: "человек работает [name]?" — если ответ "нет, это область/тема", то \
это НЕ лист, значит is_leaf=false и под ним должна быть хотя бы одна профессия \
("Живопись" → false, дочерний лист "Художник" или "Реставратор" → true).
- КАЖДЫЙ узел с is_leaf=false ОБЯЗАН иметь хотя бы одного ребёнка (узел с таким \
же parent_slug) прямо в этом же ответе — категория без единой профессии внутри \
это тупик дерева, так делать нельзя. Если не можешь придумать профессию под \
категорию — либо не добавляй категорию, либо сделай её саму is_leaf=true.
- НЕ повторяй уже существующие slug — они перечислены отдельно, их трогать нельзя.
- Не выдумывай профессии, которых реально не существует.
- Это офлайн-черновик: человек проверит и отредактирует перед добавлением в БД — \
не указывай веса по осям, возрастные метки или описания, только структуру дерева.
"""


def build_messages(
    existing_slugs: list[str],
    focus_area: str,
    count: int = 10,
) -> list[dict[str, str]]:
    existing = ", ".join(existing_slugs) if existing_slugs else "(каталог пока пуст)"
    user_content = (
        f"Существующие slug (не повторять, можно использовать как parent_slug):\n{existing}\n\n"
        f"Область для расширения: {focus_area or 'любая, на твой выбор'}\n\n"
        f"Предложи примерно {count} новых узлов дерева (можно на нескольких уровнях "
        "глубины за один раз) по заданной схеме."
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
