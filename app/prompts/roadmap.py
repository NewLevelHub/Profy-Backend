"""Roadmap generation prompt + strict output schemas for the LLM.

Two call shapes now (product decision 2026-08-18 — mixing two directions'
tasks into one milestone list, tagged by `path`, read as an incoherent plan
with no clear goal; user feedback: "к чему готовится ребёнок?"):

1. `build_messages` — the original single-call shape (ROADMAP_JSON_SCHEMA):
   milestones + focus_summary + recommended_paths together. Used as-is for
   profession/university (recommended_paths always []), and as the FIRST
   call for explore/unsure too — it's what decides recommended_paths
   (grounded in the student's full evidence, not just their RIASEC/MI score,
   so it still needs the model). If that first call names only 0-1 paths,
   its own milestones ARE the plan, unchanged from before.

2. `build_track_messages` — new. Only when the first call named exactly 2
   recommended_paths: called once PER path, each time with that one
   direction as the sole, fixed focus (TRACK_JSON_SCHEMA: milestones only,
   no recommended_paths/focus_summary — those are already decided). Produces
   two fully independent, internally coherent 5-milestone plans instead of
   one shared list with tasks tagged by which path they belong to.

Post-validation in the caller: `_valid_milestones` (shared by both shapes)
+ one corrective retry — same pattern as `direction_roadmap._valid_stages`.
"""
from app.prompts._locale import glossary_block, language_directive
from app.schemas.student_context import StudentContext

HORIZONS = ["month_1", "months_3", "months_6", "year_1", "until_goal"]

CATEGORIES = [
    "explore", "planning", "knowledge", "skill", "practice", "portfolio",
    "career", "education", "requirement", "exam", "documents", "application",
    "finance", "admission",
]

_TASK_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text", "description", "category", "priority"],
    "properties": {
        "text": {"type": "string"},
        "description": {"type": "string"},
        "category": {"type": "string", "enum": CATEGORIES},
        "priority": {"type": "integer"},
    },
}

_MILESTONES_SCHEMA: dict = {
    "type": "array",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["horizon", "title", "outcome", "tasks"],
        "properties": {
            "horizon": {"type": "string", "enum": HORIZONS},
            "title": {"type": "string"},
            "outcome": {"type": "string"},
            "tasks": {"type": "array", "items": _TASK_SCHEMA},
        },
    },
}

# Strict JSON schema for OpenAI Structured Outputs (matches RoadmapMilestone/Task).
# recommended_paths is only meaningfully filled for goal in (explore, unsure) —
# see _SYSTEM_PROMPT; for profession/university the model returns [] and
# post-validation does not require otherwise.
ROADMAP_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["milestones", "focus_summary", "recommended_paths"],
    "properties": {
        "focus_summary": {"type": "string"},
        "recommended_paths": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["key", "label", "why", "future_benefit"],
                "properties": {
                    "key": {"type": "string"},
                    "label": {"type": "string"},
                    "why": {"type": "string"},
                    "future_benefit": {"type": "string"},
                },
            },
        },
        "milestones": _MILESTONES_SCHEMA,
    },
}

# Per-path follow-up call (build_track_messages) — the direction is already
# decided and fixed, so nothing to name or summarize, just the plan itself.
TRACK_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["milestones"],
    "properties": {
        "milestones": _MILESTONES_SCHEMA,
    },
}

_GOAL_FRAMING = {
    "explore": (
        "Ученик хочет понять себя. Сначала назови 1-2 ведущих направления "
        "(recommended_paths) — не список проб без выводов, а конкретную "
        "гипотезу, куда ему стоит смотреть, с обоснованием. Если направление "
        "реально только одно (профиль однозначный) — верни один объект, не "
        "придумывай второе ради количества; тогда milestones строй сразу как "
        "полноценный план ПО ЭТОМУ направлению (та же логика эскалации, что "
        "и у profession — без пункта «выбери», без параллельных попыток). "
        "Если направлений два — не строй milestones под оба сразу: этот "
        "вызов используется только чтобы выявить и обосновать оба "
        "направления, а полный план под каждое строится отдельным вызовом "
        "позже. В этом случае построй milestones просто как общую разведку "
        "первого месяца по обоим направлениям, без специализации дальше — "
        "специализацию возьмёт на себя отдельный вызов на каждое направление."
    ),
    "unsure": (
        "Ученик пока не определился. Та же логика, что и для «разобраться "
        "в себе»: определи 1-2 ведущих направления (recommended_paths) с "
        "обоснованием; если только одно — milestones сразу полноценный план "
        "по нему; если два — milestones этого вызова нужны только как черновая "
        "разведка (полные отдельные планы строятся другим вызовом на каждое "
        "направление)."
    ),
    "profession": (
        "Ученик выбирает профессию. Эскалация ведёт от знакомства к "
        "практике: month_1 — конкретные пробы профессии, months_6 — первый "
        "учебный проект и начало портфолио, until_goal — реальный первый "
        "опыт (стажировка, волонтёрство рядом со сферой, самостоятельный "
        "проект)."
    ),
    "university": (
        "Ученик готовится к поступлению. Эскалация ведёт от разведки "
        "требований к их закрытию: month_1 — конкретный список требований "
        "и дедлайнов (используй gap-анализ ученика, если он есть в данных, "
        "чтобы month_1 бил именно в его пробелы), months_6 — документы и "
        "портфолио в работе, until_goal — поданная заявка."
    ),
}

# Shared between the main prompt and the per-track follow-up — nothing here
# depends on whether this call is deciding directions or building one plan.
def _shared_rules(locale: str = "ru") -> str:
    glossary = glossary_block(locale)
    glossary_section = f"\n\n{glossary}" if glossary else ""
    return f"""\
СТРУКТУРА. Ровно 5 этапов (milestones) — по одному на каждый горизонт: \
month_1, months_3, months_6, year_1, until_goal. В каждом этапе — от 4 до 5 \
задач (tasks), не меньше и не больше: этап обязан реально заполнять свой срок \
(месяц — это не один вечер с видео), но не парализовать длиной списка. Задачи \
внутри этапа идут по priority (1 — делать первой, дальше по порядку) и \
образуют не набор случайных советов, а маленькую последовательность с общей \
логикой этапа — например, «две разные пробы → сверка, что зашло → один \
конкретный шаг, закрывающий этап».

ЭСКАЛАЦИЯ МЕЖДУ ЭТАПАМИ ОБЯЗАТЕЛЬНА и идёт по ОДНОМУ направлению от начала \
до конца — в продукте нет трекинга и галочек, ученик не отчитывается о \
прогрессе, поэтому усложнение нужно закладывать заранее, в самом плане: \
month_1 — конкретная первая проба/знакомство, months_3 — регулярный формат \
и первый шаг за рамки инструкции, months_6 — специализация и предъявление \
результата кому-то (не только себе), year_1/until_goal — следующий виток \
сложности от уже сделанного и выход на публичный результат (конкурс, \
соревнование, показ, портфолио, заявка — по контексту цели). НЕ пиши пункт \
«выбери между X и Y» — направление уже одно, выбор не нужен.

НОЛЬ ДОДУМЫВАНИЯ — главное правило поля text. text называет конкретное \
действие, а не категорию. «Кружок» — не задача, «сходи один раз на пробное \
занятие в кружок лепки» — задача. «Видео по теме» — не задача, «посмотри \
видео о том, как рисуют покадровую мультипликацию» — задача. «Изучи \
алгоритмы» — не задача, «пройди тему "сортировка пузырьком" и реши 10 задач» \
— задача. Проверка перед тем как писать text: если ученику или родителю после \
прочтения всё ещё нужно решить, ЧТО именно делать — перепиши.

ЗАПРЕТ НА ВЫДУМКУ. При этом НЕЛЬЗЯ выдумывать точные названия конкретных \
курсов, каналов, книг, кружков, платформ, организаций или ссылки — базы \
контента у продукта нет, и придуманное существующим не является. \
Конкретность даётся ТЕМОЙ и ДЕЙСТВИЕМ, а не брендом: не «пройди курс "Python \
для всех" на Coursera», а «пройди любой бесплатный вводный курс по теме \
"переменные, циклы, списки"»; не «посмотри ролик "Как рисуют мультфильмы" на \
канале X», а «посмотри видео о том, как рисуют покадровую мультипликацию».

description раскрывает задачу — не одним общим предложением. Каждое \
предложение обязано либо (а) объяснить, почему это подходит именно ЭТОМУ \
ученику со ссылкой на конкретный сигнал из его данных, либо (б) дать понятный \
признак «готово» / как понять, что шаг выполнен. text уже несёт «что делать» \
— не дублируй его в description. Запрещены общие фразы без конкретики («это \
полезный навык», «попробуй разное», «многим нравится») — если предложение не \
делает (а)/(б), не пиши его.

МАКСИМАЛЬНАЯ ВЫЖИМКА ИЗ ДАННЫХ УЧЕНИКА. Работай как чек-лист, а не как выбор \
красивых деталей: пройдись по всем сильным сигналам ученика, относящимся к \
ЭТОМУ направлению — коду/сильным сторонам, артефактам (кружки, секции, \
достижения), лёгким и любимым предметам — и для каждого найди хотя бы один \
конкретный шаг где-то в плане. Не бери 1-2 самых ярких и не игнорируй \
остальное.

Тон и сложность — строго по возрасту (age_group):
- junior и middle: простой, тёплый язык, обращение на «ты». БЕЗ терминов и \
жаргона (ML, AI, DevOps, SQL, backend и т.п.). Действия — кружки, книги, \
простые проекты, наблюдения, игры, поездки — но именно КОНКРЕТНЫЕ, не \
абстрактные.
- senior: можно профессиональные термины, онлайн-курсы, олимпиады, стажировки, \
а при цели поступления — университеты, экзамены и документы.

Персонализация: опирайся на RIASEC-код ученика (code), сильные и слабые \
стороны (strengths/weaknesses), любимые и сложные предметы (subjects_*), \
артефакты (artifacts) и подобранные направления (careers).

Дополнительно: там, где это реально объясняет выбор конкретного шага, можно \
опереться на personality_notes (стиль работы) и \
motivation_top/motivation_highlights (что его драйвит). Используй, только \
если черта или мотив реально относятся к конкретной задаче. Никогда не \
цитируй числа (ни проценты RIASEC, ни баллы личности) — только сам тип/черту \
словами. И никогда не наклеивай ярлык типа личности («ты интроверт», «у тебя \
высокий N») — пересказывай personality_notes своими словами, через поведение \
и предпочтения, как они уже сформулированы там.

Локальные возможности: используй город (city) и страну (country), чтобы \
предлагать реальные местные форматы — кружки, школы, бесплатные программы, \
олимпиады. Формулируй как «найди в своём городе кружок…», не как выдуманный \
конкретный адрес или название организации.

{language_directive(locale)}{glossary_section}"""


def _system_prompt(locale: str = "ru") -> str:
    rules = _shared_rules(locale)
    return f"""\
Ты — не тёплый собеседник, а проектировщик учебного плана. Твоя задача — по \
данным профтеста построить роадмап, который ученик (а для 6-9 лет — его \
родитель) откроет и СРАЗУ начнёт выполнять, ничего не додумывая сам. Если шаг \
оставляет ученику решить, ЧТО конкретно делать — шаг не готов, это брак.

Отвечай СТРОГО в JSON по заданной схеме, без текста вне JSON.

ФОКУС. В поле focus_summary на корневом уровне напиши короткий «портрет» \
ученика: 2-3 предложения от второго лица («судя по твоим ответам, тебе...»), \
которые называют его сильные стороны и интересы конкретно, со ссылкой на его \
данные — не общий шаблон, а то, что реально видно именно в ЭТОМ профиле.
В поле outcome для каждого этапа milestone опиши одной понятной фразой, что \
у ученика будет на руках или в плане опыта к концу этого горизонта (например: \
«Понимание своих интересов и первых проб в разных сферах», «Первый \
практический опыт и сужение круга интересов»).

ВЕДУЩЕЕ НАПРАВЛЕНИЕ (recommended_paths) — только для goal = explore/unsure. \
Для profession/university верни recommended_paths: [] (направление уже \
задано целью). Для explore/unsure: определи по профилю 1-2 самых явных \
направления (не больше двух — если откликов больше, оставь два самых сильных \
по совпадению кода/сильных сторон/любимых предметов/артефактов) и опиши \
каждое объектом {{key, label, why, future_benefit}}:
- key — короткий идентификатор («A», «B»).
- label — название направления понятным языком («Робототехника», а не «Investigative-R»).
- why — 2-3 предложения, почему ИМЕННО ЭТОМУ ученику подходит именно это направление, с \
опорой на конкретный сигнал из его данных (код, сильная сторона, любимый предмет, артефакт) \
— не общая фраза «многим нравится».
- future_benefit — конкретно, куда это может привести дальше (кружок/секция более высокого \
уровня, олимпиада/конкурс, направление профессий, что это даёт для поступления) — без воды \
и без выдуманных названий организаций.

{rules}"""


def _track_system_prompt(locale: str = "ru") -> str:
    rules = _shared_rules(locale)
    return f"""\
Ты — не тёплый собеседник, а проектировщик учебного плана. Ученику уже \
подобрано ОДНО конкретное направление (передано ниже вместе с обоснованием, \
почему оно ему подходит) — твоя задача построить по нему полноценный \
5-этапный план, как если бы это направление было единственной целью \
ученика с самого начала. Никаких других направлений, никакого пункта \
«выбери» — план ведёт вглубь именно этого направления с первого месяца.

Отвечай СТРОГО в JSON по заданной схеме, без текста вне JSON.

В поле outcome для каждого этапа milestone опиши одной понятной фразой, что \
у ученика будет на руках или в плане опыта к концу этого горизонта.

{rules}"""


_SHARED_RULES = _shared_rules("ru")
_SYSTEM_PROMPT = _system_prompt("ru")
_TRACK_SYSTEM_PROMPT = _track_system_prompt("ru")

# Appended when a generated plan breaks the structure — one corrective pass
# beats an immediate fallback to the (much thinner) template.
RETRY_HINT: dict[str, str] = {
    "role": "user",
    "content": (
        "Твой предыдущий ответ нарушил структуру или требование конкретности. "
        "Исправь строго:\n"
        "- ровно 5 этапов: month_1, months_3, months_6, year_1, until_goal;\n"
        "- в КАЖДОМ этапе от 4 до 5 задач (не меньше 4, не больше 5), каждый "
        "milestone заполняет свой outcome;\n"
        "- каждая задача (text) называет конкретное действие, а не категорию — "
        "если задачу можно выполнить, просто погуглив 'что это значит', она "
        "недостаточно конкретна;\n"
        "- план ведёт ОДНО направление от начала до конца, без пункта "
        "«выбери между X и Y».\n"
        "Верни полный план заново по схеме."
    ),
}

# Same shape, for the first call (which also carries focus_summary/
# recommended_paths — see RETRY_HINT for the plan-structure half of this).
DECISION_RETRY_HINT: dict[str, str] = {
    "role": "user",
    "content": (
        "Твой предыдущий ответ нарушил структуру или требование конкретности. "
        "Исправь строго:\n"
        "- поле focus_summary заполнено (2-3 предложения, конкретно про этого ученика);\n"
        "- ровно 5 этапов: month_1, months_3, months_6, year_1, until_goal, "
        "в каждом от 4 до 5 задач, каждый milestone заполняет свой outcome;\n"
        "- каждая задача (text) называет конкретное действие, а не категорию;\n"
        "- если goal = explore/unsure: recommended_paths не пустой (1-2 записи), "
        "у каждой заполнены why и future_benefit со ссылкой на конкретные "
        "данные ученика;\n"
        "- если goal = profession/university: recommended_paths — [].\n"
        "Верни полный ответ заново по схеме."
    ),
}


def build_messages(context: StudentContext, *, locale: str | None = None) -> list[dict[str, str]]:
    target_locale = locale or getattr(context, "locale", "ru")
    framing = _GOAL_FRAMING.get(context.goal, _GOAL_FRAMING["explore"])
    allowed = ", ".join(CATEGORIES)
    user_content = (
        f"{framing}\n\n"
        f"Разрешённые значения category: {allowed}.\n\n"
        f"Данные ученика (JSON):\n{context.model_dump_json(indent=2)}\n\n"
        "Составь для этого ученика персональный роадмап по схеме."
    )
    return [
        {"role": "system", "content": _system_prompt(target_locale)},
        {"role": "user", "content": user_content},
    ]


def build_track_messages(
    context: StudentContext,
    path_label: str,
    path_why: str,
    path_future_benefit: str,
    *,
    locale: str | None = None,
) -> list[dict[str, str]]:
    """Follow-up call for one already-decided RecommendedPath — builds its
    full, independent 5-milestone plan (TRACK_JSON_SCHEMA)."""
    target_locale = locale or getattr(context, "locale", "ru")
    allowed = ", ".join(CATEGORIES)
    user_content = (
        f"НАПРАВЛЕНИЕ ЭТОГО ПЛАНА: «{path_label}».\n"
        f"Почему оно подходит этому ученику: {path_why}\n"
        f"Куда оно ведёт: {path_future_benefit}\n\n"
        f"Разрешённые значения category: {allowed}.\n\n"
        f"Данные ученика (JSON):\n{context.model_dump_json(indent=2)}\n\n"
        "Построй полный 5-этапный план по этому направлению, по схеме."
    )
    return [
        {"role": "system", "content": _track_system_prompt(target_locale)},
        {"role": "user", "content": user_content},
    ]
