"""Direction roadmap prompt + strict output schema.

Each stage is a flat, ordered list of steps rather than a fixed pair of tracks:
every step is tagged `profile` (deepen the direction's core skill), `growth`
(attack the weak spot that would hold the student back) or `integration` (work
that needs both). The model decides how many of each a given stage needs — but
every stage must carry at least one `growth` step, or the feature loses its point.

Structured Outputs (strict mode) forbids minItems/maxItems, so "exactly 4 stages,
3-5 steps each" is asked for in the prompt and enforced by post-validation in the
caller (`_valid_stages`).
"""
import json

from app.models.direction import Direction
from app.schemas.roadmap import DIRECTION_HORIZONS, STEP_TRACKS
from app.schemas.student_context import StudentContext

CATEGORIES = [
    "knowledge", "skill", "practice", "project", "portfolio",
    "soft_skill", "subject", "community", "exam", "university",
]

_STEP_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text", "description", "track", "category", "priority"],
    "properties": {
        "text": {"type": "string"},
        "description": {"type": "string"},
        "track": {"type": "string", "enum": STEP_TRACKS},
        "category": {"type": "string", "enum": CATEGORIES},
        "priority": {"type": "integer"},
    },
}

_STAGE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["horizon", "title", "outcome", "steps", "integration_project"],
    "properties": {
        "horizon": {"type": "string", "enum": DIRECTION_HORIZONS},
        "title": {"type": "string"},
        "outcome": {"type": "string"},
        "steps": {"type": "array", "items": _STEP_SCHEMA},
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
            "required": ["weakness", "why_it_matters", "evidence"],
            "properties": {
                "weakness": {"type": "string"},
                "why_it_matters": {"type": "string"},
                "evidence": {"type": "string"},
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

ТОЧКА РОСТА (growth_focus) — САМОЕ ОТВЕТСТВЕННОЕ МЕСТО. Здесь запрещено \
догадываться и «дорисовывать» правдоподобную слабость. Работает только то, что \
ПОДТВЕРЖДЕНО данными ученика.

Допустимые источники — ТОЛЬКО эти три:
1) inquiry.low_signals — утверждения, с которыми ученик НЕ согласился (самый сильный \
сигнал);
2) weaknesses — RIASEC-типы с самым низким баллом (профиль ученика);
3) subjects_hard / subjects_disliked — но только если предмет реально нужен в этом \
направлении (химия не нужна backend-разработчику — не бери её).

В поле evidence ОБЯЗАН указать конкретный сигнал, из которого сделал вывод: \
процитируй утверждение из low_signals, или назови тип из weaknesses с его баллом \
из profile, или назови предмет. Если подставить в evidence нечего — значит, ты \
выдумал слабость. Так делать нельзя.

ЕСЛИ ВЫРАЖЕННОЙ СЛАБОСТИ НЕТ (low_signals пуст, weaknesses не мешают этому \
направлению) — НЕ ИЗОБРЕТАЙ ЕЁ. Не пиши про публичные выступления, общение или \
прокрастинацию, если в данных этого нет. В этом случае возьми из weaknesses самый \
низкий релевантный направлению тип и сформулируй его как ЗОНУ УСИЛЕНИЯ, а не как \
недостаток: в weakness — что усилить, в why_it_matters — честно скажи, что явных \
слабых мест нет и это скорее следующий уровень мастерства, в evidence — что именно \
низкое.

Точка роста НЕ может быть профильным навыком направления (не «программирование» для \
IT, не «владение Figma» для дизайна) — этому он и так учится в profile-шагах.
В why_it_matters объясни мягко и по делу, без осуждения.
Все growth-шаги в этапах должны бить именно в эту точку роста.

ЭТАПЫ (stages) — ровно 4: months_3, months_6, months_9, months_12. В каждом этапе \
3-5 ШАГОВ (steps) — это единый упорядоченный список, а не две колонки. У каждого \
шага есть тег track:
- profile — углубление в профильный навык направления;
- growth — прицельная работа над точкой роста (слабым местом);
- integration — работа, где нужны СРАЗУ и профильный навык, и подтянутая слабая \
сторона.
Сколько каких шагов нужно в конкретном месяце — решаешь ТЫ, исходя из логики \
развития. Не надо искусственно делить поровну. Жёсткое правило одно: ни один этап не \
теряет ни профильную работу, ни работу над точкой роста. Шаг integration \
засчитывается за обе сразу (в нём есть и профиль, и рост), поэтому этап вида \
[integration, integration, growth] — валиден. priority задаёт порядок шагов внутри \
этапа (1 — первый).

ОПИСАНИЕ ШАГА (description) — САМОЕ ВАЖНОЕ. Ученик — подросток, он НЕ должен \
ничего догугливать, чтобы понять шаг. text — короткое название шага. \
description — 3-5 предложений, где ты РАЗЖЁВЫВАЕШЬ:
1) что именно делать и с чего начать (конкретные темы, понятия, шаги — по порядку);
2) зачем это нужно и как это связано с конечной целью (target.role);
3) как понять, что задача выполнена — измеримый признак («сможешь сам написать…», \
«решаешь такие задачи без подсказки», «у тебя есть готовый…»).
Плохо: «Изучи основы алгоритмов». Хорошо: «Начни с самого базового: что такое \
сложность алгоритма (нотация O-большое), массивы и списки, сортировка пузырьком и \
бинарный поиск. Разбирай по одной теме в неделю и сразу пиши код руками, не \
подглядывая. Именно это отличает того, кто "умеет писать код", от разработчика: на \
собеседованиях и олимпиадах спрашивают ровно это. Готово, когда сможешь без \
подсказки объяснить, почему бинарный поиск быстрее перебора, и написать оба.»
Не используй жаргон без расшифровки: если пишешь термин — тут же поясняй его \
простыми словами.

ИТОГ ЭТАПА (outcome) — 1-2 предложения: что у ученика БУДЕТ на руках к концу этапа \
(навык, проект, результат) и как это приближает его к target.role. Ученик должен \
видеть, к чему всё ведёт, а не просто список дел.

Логика этапов:
- months_3 — база и теория: profile-шаги осваивают основы; growth-шаг закрывает \
пробел (курс, учебник, разбор конкретных тем). Шагов track=integration здесь нет, \
integration_project = null.
- months_6 — практика и выход из зоны комфорта: profile-шаги дают первую реальную \
практику; growth-шаг ведёт туда, где слабый навык НУЖЕН вживую (кружок, секция, \
клуб, школьное сообщество). integration_project = null.
- months_9 — интеграция: добавь шаг(и) track=integration — ОДИН проект, где нужны \
сразу и профильный навык, и подтянутая слабая сторона. Опиши его в \
integration_project. Пример: взять интервью у трёх незнакомых людей — это и \
журналистика, и преодоление страха общения.
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


# Appended when a generated plan breaks the structural rules — the model is
# inconsistent about them, and one corrective pass is cheaper than a 503.
RETRY_HINT: dict[str, str] = {
    "role": "user",
    "content": (
        "Твой предыдущий ответ нарушил структуру. Исправь строго:\n"
        "- ровно 4 этапа: months_3, months_6, months_9, months_12;\n"
        "- в КАЖДОМ этапе минимум 3 шага;\n"
        "- в КАЖДОМ этапе есть профильная работа (track=profile или integration) "
        "И работа над точкой роста (track=growth или integration).\n"
        "Верни полный план заново по схеме."
    ),
}


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
