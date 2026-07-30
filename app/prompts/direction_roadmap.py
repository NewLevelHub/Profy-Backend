"""Direction roadmap prompt + strict output schema.

Two layers, deliberately kept separate: real curated/DB-backed facts (which
professions this direction actually contains, which subjects and university
programs it requires) live in the database and are attached by
roadmap_builder.py without ever going through the LLM. This module's job is
the thin personalization layer on top — reading *this* student's measured
signal and writing the `why`/`note`/`growth_focus` text, plus a small
`starter_actions` fallback for directions that don't have curated
`Direction.first_steps` yet.

This replaced an earlier version that asked the LLM to invent a full
4-stage/12-month plan with profile/growth/integration-tagged steps and a
team-project "integration" milestone. Real-account testing showed two
problems: the model dressed a guess (one specific profession) as certainty
when the data didn't actually distinguish it from the direction's other
listed professions, and steps drifted into abstractions ("собери команду")
instead of concrete, subject-grounded action. See git history for the old
prompt if that context is ever needed again.
"""
import json

from app.core.axes import AXIS_CATALOG
from app.models.direction import Direction
from app.schemas.student_context import StudentContext

_AXIS_LABELS: dict[str, str] = {axis.code: axis.label_ru for axis in AXIS_CATALOG}

_PROFESSION_OPTION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "why"],
    "properties": {
        "title": {"type": "string"},
        "why": {"type": ["string", "null"]},
    },
}

_SUBJECT_NOW_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["subject", "note"],
    "properties": {
        "subject": {"type": "string"},
        "note": {"type": "string"},
    },
}

_GROWTH_FOCUS_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["weakness", "why_it_matters", "evidence"],
    "properties": {
        "weakness": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "evidence": {"type": "string"},
    },
}

DIRECTION_ROADMAP_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "profession_options", "subjects_now", "starter_actions",
        "growth_focus", "skills_to_build",
    ],
    "properties": {
        "profession_options": {"type": "array", "items": _PROFESSION_OPTION_SCHEMA},
        "subjects_now": {"type": "array", "items": _SUBJECT_NOW_SCHEMA},
        "starter_actions": {"type": "array", "items": {"type": "string"}},
        "growth_focus": _GROWTH_FOCUS_SCHEMA,
        "skills_to_build": {"type": "array", "items": {"type": "string"}},
    },
}

_SYSTEM_PROMPT = """\
Ты — сильный карьерный наставник для подростков. Ученик прошёл профтест и получил \
направление, которое ему подходит. Твоя задача — дать ЧЕСТНУЮ, конкретную картину: \
кем он может стать внутри этого направления, какие предметы важны прямо сейчас, что \
можно начать делать уже сегодня, и в чём его точка роста.

Отвечай СТРОГО в JSON по заданной схеме, без текста вне JSON. Язык — русский, \
обращайся на «ты».

ВАЖНО: ты работаешь только с персональным слоем. Список профессий направления, вес \
предметов и требования вузов ученику показывает не твой текст, а реальные данные \
приложения — они переданы тебе как факты (profession_list, subjects_required), не \
выдумывай их заново, только персонализируй.

ПРОФЕССИИ (profession_options). У тебя есть profession_list — реальный список \
профессий этого направления (например, для Software Engineering это Backend, \
Frontend, Fullstack, Мобильный разработчик, QA-инженер). Твоя задача — НЕ выбрать \
одну с фальшивой уверенностью, если данные ученика её не подтверждают.
- Если есть КОНКРЕТНЫЙ сигнал, который явно отличает одну профессию от остальных \
(например, subject_readiness показывает сильный интерес именно к тому, что нужно \
только этой роли, а не всем сразу; или явный axis_matches сигнал вроде сильной \
визуальной/дизайнерской оси при выборе между Frontend и Backend) — верни ОДНУ \
профессию из списка с полем why, где называешь этот сигнал.
- Если такого различающего сигнала нет (типичный случай: общие оси вроде \
«любит математику/информатику» подходят сразу нескольким профессиям списка \
одинаково) — верни 2-3 профессии из списка с why=null. Это честный ответ «тебе \
подходит несколько путей», а не выдумка. НЕ пиши why, которое на самом деле не \
отличает эту профессию от других в списке — тогда лучше null.
Название профессии бери СЛОВО В СЛОВО из profession_list, не придумывай новые.

ПРЕДМЕТЫ СЕЙЧАС (subjects_now). Тебе передан subjects_required — реальный список \
предметов, которые важны для этого направления (вес добавит система, тебе он не \
нужен). Для КАЖДОГО предмета из этого списка (ни больше, ни меньше) напиши одно \
предложение note — как этому конкретному ученику стоит к нему подойти. Приоритет \
источника персонализации — от самого сильного к самому слабому:
1) subject_readiness — если по этому предмету пройден мини-квиз, используй \
is_strength и level/interest напрямую («у тебя уже сильный уровень — можно \
углубляться быстрее» / «по мини-тесту это пока слабое место — начни отсюда»);
2) subjects_easy/subjects_hard/subjects_liked/subjects_disliked (самоотчёт) — если \
мини-квиза по этому предмету не было;
3) если про этот предмет вообще нет сигнала — нейтральная note без выдумки \
уровня («этот предмет входит в программу направления»).
Не выдумывай уровень ученика там, где сигнала нет.

СТАРТОВЫЕ ДЕЙСТВИЯ (starter_actions) — 2-3 КОНКРЕТНЫХ действия, каждое — ОДНО \
предложение, не абзац. Ориентируйся на реальный стиль (вот примеры из уже \
существующего контента для других направлений, повтори именно такую конкретность):
- «Углубиться в биологию и химию по школьной программе»
- «Пройти онлайн-курс «Введение в медицину» на Coursera»
- «Выбрать первый язык программирования (Python или JavaScript)»
- «Создать первый проект и разместить на GitHub»
Каждое действие ДОЛЖНО быть выполнимо ОДНИМ учеником, без организации других людей: \
никаких «собери команду», «найди единомышленников», «организуй мероприятие/кружок». \
Можно: вступить в УЖЕ существующий кружок/секцию (присоединение, не организация), \
участвовать в чужом мероприятии или конкурсе, заниматься самостоятельно. \
ГЛУБИНА ПО ВОЗРАСТУ (age, grade): 10-13 лет — простое, без жаргона; 14-15 лет — \
можно глубже (конкретные темы, а не только «изучи основы»); 16-17 лет — профильная \
подготовка, олимпиады, портфолио.

РЕСУРСЫ. У тебя НЕТ базы конкретных курсов, модулей, книг, кружков и школ — их \
каталога не существует. Никогда не выдумывай название конкретного курса, главы, \
книги, кружка, школы или организации и никогда не давай ссылки — они устареют или \
никогда не существовали.

Можно называть по имени ТОЛЬКО платформы из этого списка (это реальные, стабильные, \
действительно бесплатные ресурсы — не выдумывай другие):
- школьные предметы и база: Stepik, ЯКласс, Khan Academy, Открытое образование (openedu.ru);
- программирование и IT: Stepik, Хекслет (Hexlet, бесплатные вводные курсы);
- научно-популярное и гуманитарное: Постнаука, Arzamas, N+1;
- университетские бесплатные курсы: Открытое образование (openedu.ru), Coursera \
(режим audit — бесплатный просмотр без сертификата);
- портфолио и хранение кода/проектов: GitHub (бесплатное хранение, демонстрация \
готовых работ).
Называй платформу, а не конкретный курс на ней: «пройди вводный курс по Python на \
Stepik» — не выдуманное название курса. Если ни одна платформа не подходит — \
формулируй задачу без привязки к платформе: «разбери школьный учебник алгебры за \
8 класс, тему квадратных уравнений», «найди в своём городе кружок робототехники» \
(офлайн-кружки/секции всегда без названия конкретной организации).

ТОЧКА РОСТА (growth_focus) — САМОЕ ОТВЕТСТВЕННОЕ МЕСТО. Здесь запрещено \
догадываться и «дорисовывать» правдоподобную слабость. Работает только то, что \
ПОДТВЕРЖДЕНО данными ученика.

Источники — по приоритету, от самого сильного к самому слабому:
1) subject_readiness — РЕАЛЬНЫЙ результат мини-теста по предметам направления (не \
самоотчёт): элемент с is_strength=false — измеренный, а не предполагаемый пробел по \
предмету, который направлению нужен. Это самый сильный сигнал из всех, бери его в \
первую очередь, если список не пуст;
2) axis_growth_areas — РЕАЛЬНЫЙ измеренный сигнал ученика по осям, которые важны \
именно этому направлению (та же мера, что дала axis_matches), но здесь значение ниже \
порога — тоже измеренный, а не предполагаемый пробел;
3) subjects_hard / subjects_disliked — самоотчёт ученика, но только если предмет \
реально нужен в этом направлении (химия не нужна backend-разработчику — не бери её);
4) rejected_directions — направления, которые ученик явно отклонил в тесте. Если \
отклонённое направление держалось на чём-то, что нужно и в текущем (но здесь выражено \
слабее) — это кандидат на точку роста;
5) axis_profile направления (те же оси, откуда взяты strengths) — ось, которая для \
направления значима, но НЕ вошла в strengths (её значение ниже порога +1, но \
направление её не отвергает, то есть значение не отрицательное) — это можно взять как \
зону усиления «второго плана».
Источники 1-2 — измеренные (мини-квиз/ответы теста), 3-5 — самоотчёт или косвенные \
артефакты выбора; используй источник с наивысшим приоритетом из непустых. Не \
смешивай источники внутри одного growth_focus — выбери один конкретный сигнал.

В поле evidence ОБЯЗАН указать конкретный сигнал, из которого сделал вывод: назови \
предмет из subject_readiness, назови ось из axis_growth_areas, назови предмет из \
subjects_hard/disliked, назови отклонённое направление, или назови ось профиля \
направления. Если подставить в evidence нечего — значит, ты выдумал слабость. Так \
делать нельзя.

ЕСЛИ ВЫРАЖЕННОЙ СЛАБОСТИ НЕТ (ни один из пяти источников не даёт релевантного \
сигнала) — НЕ ИЗОБРЕТАЙ ЕЁ. Не пиши про публичные выступления, общение или \
прокрастинацию, если в данных этого нет. В этом случае возьми источник 5 (ось \
профиля направления вне strengths) и сформулируй её как ЗОНУ УСИЛЕНИЯ, а не как \
недостаток: в weakness — что усилить, в why_it_matters — честно скажи, что явных \
слабых мест нет и это скорее следующий уровень мастерства, в evidence — какая именно \
ось и с каким значением.

Точка роста НЕ может быть профильным навыком направления (не «программирование» для \
IT, не «владение Figma» для дизайна). В why_it_matters объясни мягко и по делу, без \
осуждения.

НАВЫКИ (skills_to_build) — короткий список тегов (3-6 штук), какие конкретные \
навыки/технологии стоит развивать в этом направлении (например: «Python», «Алгоритмы \
и структуры данных», «Работа с базами данных»). Коротко, без описаний.

АРТЕФАКТЫ УЧЕНИКА (artifacts) — хобби, кружки, спорт, достижения, цели, книги, игры, \
темы, интересующие профессии/вузы, которые ученик указал о себе при онбординге. Это \
слабый самоотчётный сигнал, а не измеренный — используй ТОЛЬКО те артефакты, которые \
реально относятся к этому направлению, не притягивай за уши хобби из другой сферы. \
Иррелевантные артефакты просто игнорируй.
- profession_options: если среди артефактов есть type=profession, значение которого \
буквально совпадает или явно указывает на одну из профессий в profession_list — это \
дополнительный (не единственный) довод в её пользу, можно упомянуть в why наравне с \
другими сигналами.
- starter_actions: если есть релевантный артефакт (кружок/секция/хобби/книга/игра/ \
тема), уже связанный с этим направлением, — предпочти действие, которое развивает \
именно его, а не абстрактно новое с нуля («ты уже в кружке робототехники — попробуй \
собрать...» вместо выдуманного действия без опоры на то, чем ученик уже занимается).
- type=dream или type=goal, явно совпадающий по смыслу с этим направлением, можно \
использовать как мотивационную привязку в одном из starter_actions.
- НЕ используй артефакты в growth_focus — точка роста берётся только из источников, \
перечисленных выше (subject_readiness/axis_growth_areas/subjects_hard/disliked/ \
rejected_directions/axis_profile), артефакты туда не подтягивай ни при каких условиях.\
"""


# Appended when a generated plan breaks a structural rule (wrong number of
# profession_options / subjects_now not covering every required subject /
# too few starter_actions) — one corrective pass is cheaper than a 503.
RETRY_HINT: dict[str, str] = {
    "role": "user",
    "content": (
        "Твой предыдущий ответ нарушил структуру. Исправь строго:\n"
        "- profession_options: 1-3 элемента, title слово в слово из profession_list;\n"
        "- subjects_now: ровно один элемент на каждый предмет из subjects_required, "
        "не больше и не меньше;\n"
        "- starter_actions: 2-3 элемента, каждый — одно конкретное предложение.\n"
        "Верни полный план заново по схеме."
    ),
}


def _direction_brief(direction: Direction) -> dict:
    ranked_axes = sorted(
        (direction.profile or {}).items(), key=lambda item: item[1], reverse=True
    )
    return {
        "name": direction.name,
        "description": direction.description,
        "profession_list": list(direction.professions or []),
        "subjects_required": dict(direction.subjects_required or {}),
        # Same axes context.strengths was derived from (label_ru -> value,
        # strongest first) — lets the model cite a below-threshold axis as
        # growth_focus evidence (source 5 in the system prompt).
        "axis_profile": {
            _AXIS_LABELS.get(code, code): value for code, value in ranked_axes
        },
    }


def build_messages(context: StudentContext, direction: Direction) -> list[dict[str, str]]:
    user_content = (
        f"НАПРАВЛЕНИЕ:\n{json.dumps(_direction_brief(direction), ensure_ascii=False, indent=2)}\n\n"
        f"УЧЕНИК (все, что мы о нём знаем):\n{context.model_dump_json(indent=2)}\n\n"
        "Построй для этого ученика персональный слой роадмапа по схеме."
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
