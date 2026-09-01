"""Development plan prompts + strict output schemas.

Two phases, both OpenAI Structured Outputs (strict mode — no minItems/maxItems,
counts are enforced by app/services/development_plan_validation.py):

  Phase 1  build_skeleton_messages / SKELETON_SCHEMA
           target + about_you (incl. growth point) + skills + 4 stages,
           each with 3-4 tasks as {track, title, why, done_when} — NO steps.

  Phase 2  build_stage_messages / STAGE_SCHEMA  (one call per stage)
           fills each task's steps[] -> actions[].

Curated facts (Program/University admission data, curriculum topics) are passed
in as reference only and stapled onto the result by the caller — the model
never authors them.
"""
import json

from app.schemas.development_plan import TRACKS

# ─── Stage slots by grade (backend decides these, never the model) ─────────────
STAGE_SLOTS: dict[int, list[tuple[str, str]]] = {
    11: [
        ("autumn_11", "Осень 11 класса"),
        ("winter_11", "Зима: пробный экзамен и подача"),
        ("spring_11", "Весна: финальная подготовка"),
        ("summer_11", "Лето — поступление"),
    ],
    10: [
        ("year_10", "10 класс (учебный год)"),
        ("summer_10", "Лето"),
        ("autumn_winter_11", "11 класс — осень и зима"),
        ("spring_11", "11 класс — весна и поступление"),
    ],
    9: [
        ("year_9", "9 класс"),
        ("year_10", "10 класс"),
        ("year_11", "11 класс"),
        ("admission", "Поступление"),
    ],
}

# Compulsory ENT subject that IS a real academic subject with a curriculum —
# added to subjects_needed for LOCAL-university plans only (a foreign plan has
# no ЕНТ line except an optional backup, see the foreign block).
MANDATORY_ENT_SUBJECTS: list[str] = ["история Казахстана"]

# "Математическая грамотность" and "грамотность чтения" are ЕНТ test-taking
# sections, NOT school subjects — trivial, ~1 month of prep. They get ONE
# light action near the exam, never a curriculum walk or a book.
ENT_LITERACY_NOTE = (
    "Математическая грамотность и грамотность чтения — это разделы ЕНТ, а не "
    "школьные предметы: короткий навык сдачи теста. Максимум ОДНО действие во "
    "всём плане, ближе к экзамену: «прорешай 3-4 открытых варианта за месяц до "
    "ЕНТ». Не строй вокруг них план, не предлагай книги и не давай им отдельную "
    "задачу track=ent."
)


def stage_slots_for_grade(grade: int) -> list[tuple[str, str]]:
    """Clamp anything outside 9-11 to the nearest supported grade."""
    if grade <= 9:
        return STAGE_SLOTS[9]
    if grade >= 11:
        return STAGE_SLOTS[11]
    return STAGE_SLOTS[10]


# ─── Closed vocabularies (mirrored in the validator) ──────────────────────────
# track=profession is a LIGHT garnish, not a training programme — the student
# has already chosen the direction. Heavy formats (a full course, a series of
# lessons, a portfolio of projects, regular practice) are deliberately absent.
PROFESSION_ARCHETYPES = (
    "посмотреть одну профильную лекцию, документалку или разбор (разово, не курс)",
    "прочитать одну статью или главу смежной книги (без выдуманного названия)",
    "один маленький этюд руками: набросок, замер, наблюдение с короткой заметкой",
    "подготовиться к школьному этапу олимпиады через своего учителя-предметника",
    "один разговор со специалистом сферы (можно онлайн)",
)

# Checked against text.lower() with "бесплатн" stripped first (so "платн"
# catches "платный курс" without flagging "бесплатный курс").
FORBIDDEN_MARKERS = (
    "собери команду", "собрать команду", "найди единомышленник",
    "вступи в клуб", "запишись в клуб", "выступи перед классом",
    "презентация перед классом", "защити проект перед",
    "стажировк", "менторств", "найди ментора", "найди наставника",
    "репетитор", "платн", "за деньги",
    "поступай в ниш", "поступи в ниш", "рфмш", "перейди в бил",
    "переезд в другой город", "переехать в город", "город побольше",
    "запусти бизнес", "запусти стартап", "открой ип",
)


# ─── System prompt shared by both phases ──────────────────────────────────────
_COMMON_SYSTEM = """\
Ты — сильный наставник старшеклассника из Казахстана. Ему {grade} класс, город \
{city}. Он выбрал профессию и конкретную программу вуза «{university}», \
специальность «{specialty}», и хочет план развития до поступления.

Отвечай СТРОГО в JSON по заданной схеме, без текста вне JSON. Язык — русский, \
обращение на «ты».

ЧТО РЕАЛЬНО ПОВЫШАЕТ ШАНС ПОСТУПЛЕНИЯ — это ОСНОВА плана:
- местный вуз: балл ЕНТ по профильным предметам (это почти всё);
- зарубежный вуз: языковой экзамен + заявка (эссе, портфолио если требуется, \
дедлайны, оценки в аттестате).
Плюс тонкая линия зоны роста (track=growth).

track=profession — ЛЁГКАЯ вспомогательная линия, не главная. Ученик УЖЕ выбрал \
направление; задача profession — поддержать интерес и дать пару строк в \
мотивационное письмо, а НЕ сделать из школьника джуниора. Форматы — только \
лёгкие: {archetypes}. НЕ давай курс, «серию видео для начинающих», регулярную \
практику, портфолио проектов. Если он раз в пару месяцев смотрит лекцию и \
почитывает смежное — этого достаточно.

Кружки, конкурсы, менторы, элитные школы, репетиторы — НЕ в плане.

ЗАКРЫТЫЙ СЛОВАРЬ. Тег задачи track — одно из: {tracks}. Действие track=profession \
— один из архетипов: {archetypes}.

ЗАПРЕЩЕНО ВЕЗДЕ: «собери команду», «вступи/запишись куда-то» как суть шага, \
«выступи перед классом», стажировка, менторство, «поступай в НИШ/РФМШ/БИЛ» и \
любые селективные или платные школы, репетитор, платные курсы, «переезжай в \
город побольше», бренды курсов/книг/платформ, ссылки (кроме source_url в \
фактах), выдуманные даты/баллы/суммы.

ИНВАРИАНТ: каждое действие выполнимо ОДНИМ учеником из своего города, \
бесплатно, с телефоном или компьютером. Если по смыслу нужна публика — всегда \
давай вариант «запиши видео на телефон / выложи текст / расскажи семье».

БЕЗ ЯРЛЫКОВ ЛИЧНОСТИ. Не пиши «ты интроверт», «у тебя низкий N», «ты аналитик \
по типу». Говори о поведении и предпочтениях. Не подставляй процент или балл — \
ни для RIASEC, ни для черт характера.

АНТИ-ВЫДУМКА. У тебя нет базы курсов, книг, лекций и организаций. Конкретной \
должна быть ЗАДАЧА, а не бренд: «посмотри любую вводную лекцию по теме X на \
ютубе», «разбери в школьном учебнике за 8 класс тему Y». Даты, проходные баллы \
и суммы грантов бери ТОЛЬКО из переданных фактов; если их там нет — пиши \
«уточни на сайте вуза», не выдумывай.

БЕЗ СЛУЖЕБНЫХ СЛОВ. Ученик видит только текст. НИКОГДА не пиши в нём слова \
curriculum_slice, slot, track, skeleton, «блок», «список тем» — это внутренние \
названия. Вместо «сверься со списком тем» назови сами темы словами в кавычках.

КОНТЕКСТ РК: экзамен — ЕНТ; олимпиада идёт школьный → городской → областной → \
республиканский этап, записывает на неё свой учитель-предметник. Никаких \
AP/SAT/IB для местного вуза.

ГЛУБИНА ПО ВОЗРАСТУ: 9 класс — больше проб и базовых навыков, задачи track=\
admission только в последнем этапе; 11 класс — плотно ЕНТ и admission, ранние \
дедлайны.\
"""

_FOREIGN_BLOCK = """\

ЗАРУБЕЖНЫЙ ВУЗ. Целевой вуз — за рубежом, и план ведёт именно туда.
- ПЕРВЫЙ этап НАЧИНАЕТСЯ с задачи track=language (подготовка к языковому \
экзамену {language_exam}) и с честного пути поступления. target.why ОБЯЗАНО \
начинаться с этого пути: {foreign_route}.
- track=language идёт в спине во всех этапах, с запасом по времени.
- Задачи track=admission — про ЗАРУБЕЖНЫЙ вуз: список вузов с требованиями в \
один документ, черновик и финал мотивационного эссе (personal statement), \
подача по ранним дедлайнам.
- ЕНТ и местный вуз — НЕ ведущая линия. Это ровно ОДНА задача track=admission \
во 2-м или 3-м этапе (не в первом), с явной пометкой «запасной вариант на \
случай, если по деньгам или баллам за рубеж не сложится». Не выноси её в \
начало и не делай track=ent-задач по казахстанским мандаторным предметам \
(история Казахстана, грамотности) — для зарубежного плана они не нужны.\
"""


# ─── Phase 1: skeleton ───────────────────────────────────────────────────────
_SKELETON_SYSTEM = _COMMON_SYSTEM + """\


ЭТО ФАЗА 1 — СКЕЛЕТ. Верни:

target — РЕАЛЬНОЕ, узнаваемое название профессии, которое существует на рынке \
труда и которое поймёт родитель: «архитектор», «врач-педиатр», \
«backend-разработчик», «журналист». НЕ придумывай составные и модные названия \
(«архитектор-концептуалист», «специалист по клиентскому опыту», «инженер \
будущего»). Можно уточнить сферу («архитектор жилых зданий», «детский врач»), \
но не изобретать новую должность. why — синтез: интерес по RIASEC \
(code/strengths) + 1-2 черты из personality_notes, ЕСЛИ они реально объясняют \
именно эту роль + мотивация, если в тему. Не тяни всё подряд.

about_you.strengths — 2-4 пункта из strengths / summary / thinking_style.

about_you.growth — зона роста, ТОЛЬКО если она реально есть. Определи, что \
профессия требует по характеру (2-4 качества), и пересеки с ПОДТВЕРЖДЁННЫМИ \
слабыми сторонами ученика: слабые буквы RIASEC, низкие черты personality_notes, \
трудные нужные направлению предметы. Есть пересечение — это зона роста, в \
evidence процитируй конкретный сигнал. Пересечения НЕТ — верни growth: null. НЕ \
выдумывай «зону усиления следующего уровня», не притягивай ничего. Зона роста НЕ \
может быть профильным навыком направления.

stages — РОВНО 4 этапа с переданными slot и label. В каждом: outcome (что будет \
у ученика на руках к концу этапа и как это приближает к цели) и 2-5 задач вида \
{{track, title, why, done_when}} — БЕЗ шагов (их добавит фаза 2). Не раздувай: \
обычно этап — это ent + одна лёгкая profession, иногда + growth или admission.

СОСТАВ ЭТАПА:
- track=ent — ОДНА задача в первых трёх этапах, ЕСЛИ целевой вуз в Казахстане. \
Это КОСТЯК плана: режим подготовки к ЕНТ (раскроется в фазе 2 — пробный экзамен, \
свой список пробелов, недельный объём задач, варианты на время). Заголовок \
задачи — конкретный: «Подготовка к ЕНТ: математика и информатика», не «повтори \
программу». В последнем этапе ЕНТ уже сдаётся — там задачи admission (подача, \
грант, запасные вузы), и в outcome последнего этапа добавь короткое тёплое \
пожелание (одно предложение). Зарубежный вуз — задач track=ent НЕ делай, см. \
блок ЗАРУБЕЖНЫЙ ВУЗ.
- track=profession — РОВНО ОДНА задача в КАЖДОМ этапе. Формат только лёгкий: \
посмотреть лекцию / видео / разбор или прочитать статью / главу по теме \
профессии. Разово, для поддержания интереса. НЕ курс, НЕ проект, НЕ портфолио.
- track=growth — ТОЛЬКО если about_you.growth не null. Тогда одна лёгкая задача \
примерно в двух из четырёх этапов. Иначе задач track=growth нет.
- track=language — только зарубежный вуз, см. блок ЗАРУБЕЖНЫЙ ВУЗ.

Портфолио — НЕ задача track=profession. Только если программа объективно требует \
его (архитектура/дизайн/искусство) — задача track=admission «портфолио для \
заявки», скромно: 5-8 своих работ в один файл.\
""" + ENT_LITERACY_NOTE

_STEP_SCHEMA_P1 = {
    "type": "object",
    "additionalProperties": False,
    "required": ["track", "title", "why", "done_when"],
    "properties": {
        "track": {"type": "string", "enum": list(TRACKS)},
        "title": {"type": "string"},
        "why": {"type": "string"},
        "done_when": {"type": "string"},
    },
}

SKELETON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["target", "about_you", "stages"],
    "properties": {
        "target": {
            "type": "object",
            "additionalProperties": False,
            "required": ["role", "why", "university_name", "specialty"],
            "properties": {
                "role": {"type": "string"},
                "why": {"type": "string"},
                "university_name": {"type": "string"},
                "specialty": {"type": "string"},
            },
        },
        "about_you": {
            "type": "object",
            "additionalProperties": False,
            "required": ["strengths", "growth"],
            "properties": {
                "strengths": {"type": "array", "items": {"type": "string"}},
                "growth": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "required": ["area", "why", "evidence"],
                    "properties": {
                        "area": {"type": "string"},
                        "why": {"type": "string"},
                        "evidence": {"type": "string"},
                    },
                },
            },
        },
        "stages": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["slot", "label", "outcome", "tasks"],
                "properties": {
                    "slot": {"type": "string"},
                    "label": {"type": "string"},
                    "outcome": {"type": "string"},
                    "tasks": {"type": "array", "items": _STEP_SCHEMA_P1},
                },
            },
        },
    },
}

SKELETON_RETRY_HINT = {
    "role": "user",
    "content": (
        "Твой предыдущий ответ нарушил структуру. Исправь строго:\n"
        "- РОВНО 4 этапа с переданными slot;\n"
        "- 2-5 задач в каждом этапе;\n"
        "- РОВНО ОДНА задача track=profession в КАЖДОМ этапе (лёгкая: лекция/"
        "видео/чтение);\n"
        "- для местного вуза — задача track=ent в первых трёх этапах;\n"
        "- при зарубежном вузе — хотя бы одна задача track=language;\n"
        "- track=growth — только если у ученика есть выраженная зона роста, иначе "
        "about_you.growth = null и задач track=growth нет;\n"
        "- если about_you.growth не null — в нём непустой evidence.\n"
        "Верни полный скелет заново по схеме."
    ),
}


# ─── Phase 2: expand one stage ───────────────────────────────────────────────
_STAGE_SYSTEM = _COMMON_SYSTEM + """\


ЭТО ФАЗА 2 — РАСКРЫТИЕ ОДНОГО ЭТАПА. Тебе дают этап и его задачи (title, why, \
done_when). Для КАЖДОЙ задачи верни steps[] с actions[].

ДЕЙСТВИЕ (action). Каждое предложение в text делает РОВНО одно из трёх:
(а) что конкретно делать и с чего начать — темы, понятия, шаги по порядку;
(б) связь именно с ЭТИМ учеником со ссылкой на конкретный сигнал из его данных;
(в) проверяемый критерий готовности («сможешь сам…», «10 записанных…», «есть \
готовый файл…»).
Предложения-вода («это важный навык», «тебе понравится») запрещены.

time — честная оценка: «15 мин», «~2 часа», «20 мин/день, 4 недели». kind — \
once (сделать один раз), repeat (повторять; тогда count_target — сколько раз) \
или project (пошаговый под-результат). В КАЖДОМ этапе должно быть хотя бы одно \
действие kind=repeat со счётчиком — именно оно заполняет месяц.

track=profession — РОВНО ОДНА задача, 1-2 действия, каждое разовое и лёгкое. \
Формат: посмотреть одну лекцию / видео / разбор по теме профессии ИЛИ прочитать \
одну статью / главу смежной книги (без названия). Всё. НЕ курс, НЕ серия видео, \
НЕ проект, НЕ портфолио, НЕ регулярная практика, НЕ kind=repeat. Ученик уже \
выбрал направление — задача только поддерживает интерес и даёт пару строк в \
мотивационное письмо. Пример действия: «Посмотри на ютубе любую популярную \
лекцию про работу [роль] и запиши 3 вещи, которые тебя удивили».

track=ent — это РЕЖИМ подготовки к ЕНТ на весь сезон. Раскрой задачу в ОДИН шаг \
с таким набором действий (не меньше, не «повтори программу»):

ПЕРВЫЙ этап (slot autumn_11 / year_9 / year_10):
- once: «Пройди полный пробный ЕНТ (2 профильных + история Казахстана + мат. \
грамотность + грамотность чтения), запиши балл по каждому предмету. ~4 часа.»
- once: «Сравни баллы с целевым (грантовый порог по специальности — [из фактов] \
или "уточни на сайте вуза"). По итогам пробного составь СВОЙ список пробелов: по \
каждому профильному предмету выпиши темы и типы задач, где ошибся. Проверь себя \
снизу — с задач за 7-8 класс; где начинаешь стабильно ошибаться, оттуда и \
работай вверх.»
- repeat (count_target = число недель в сезоне, ~10-12): «Каждую неделю бери 2-3 \
темы из своего списка пробелов, разбирай каждую по бесплатному видео и прорешивай \
по 25-30 задач. Цель — закрыть весь список к концу сезона. ~5-6 часов в неделю на \
профильные.» Если переданы примеры тем за 7-9 класс — вставь 1-2 в кавычках как \
иллюстрацию с чего проверять базу.

ЗИМНИЙ и ВЕСЕННИЙ этапы:
- once: «Перепройди пробный ЕНТ, сравни баллы с прошлым разом: где вырос, где \
нет. Где не сдвинулось — меняй подход (другой источник, больше задач, тема с \
нуля).»
- repeat (счётчик = недели): продолжай недельный разбор пробелов, теперь плотнее.
- repeat (счётчик): «Раз в 2 недели решай полный вариант профильного предмета на \
время, записывай результат.»
- (весенний этап) once: «Заведи список тем, где стабильно мажешь на вариантах, и \
раз в 2 недели добивай худшую.»

Не приоритизируй темы по весу в ЕНТ. В one из действий добавь строку: «в школе \
просто не отставай — подготовка к ЕНТ это отдельная работа поверх уроков».

ПРИМЕР раскрытия задачи «Подготовка к ЕНТ: математика и информатика» (осень):
steps=[{{"title":"Режим подготовки к ЕНТ","actions":[
 {{"text":"Пройди полный пробный ЕНТ (математика, информатика, история \
Казахстана, мат. грамотность, грамотность чтения) и запиши балл по каждому \
предмету.","time":"~4 часа","kind":"once","count_target":null}},
 {{"text":"Сравни баллы с грантовым порогом по специальности. По итогам пробного \
выпиши свой список пробелов по математике и информатике — конкретные темы и типы \
задач, где ошибся; проверь базу с 7-8 класса (например, "Квадратные уравнения") \
и найди, откуда начинать.","time":"~2 часа","kind":"once","count_target":null}},
 {{"text":"Каждую неделю бери 2-3 темы из своего списка пробелов, разбирай по \
бесплатному видео и прорешивай по 25-30 задач; цель — закрыть весь список к концу \
осени. В школе при этом просто не отставай.","time":"5-6 часов в \
неделю","kind":"repeat","count_target":11}}
]}}]

track=growth — ремедиация ТОЛЬКО в одиночку и измеримо: запись видео или аудио \
на телефон со счётчиком; один разговор по делу с новым человеком в неделю \
(можно онлайн-сообщением); на каждом уроке заставить себя один раз ответить или \
задать вопрос; книга по теме без названия. count_target обязателен.

track=admission / language — только из переданных фактов. Чего нет в фактах — \
«уточни на сайте вуза». Для зарубежного: пробный языковой экзамен (IELTS/TOEFL) \
— в первом этапе, дальше повторные срезы со сравнением. Документы, дедлайны, \
грант, запасные вузы — в последнем этапе. Портфолио для заявки (если факты \
говорят, что оно нужно, или специальность — архитектура/дизайн/искусство) — \
скромно: собрать 5-8 своих рисунков/набросков/работ в один PDF, без пометки \
«портфолио архитектора». (Пробный ЕНТ — это НЕ admission, это часть track=ent, \
см. выше.)""" + "\n\n" + ENT_LITERACY_NOTE + """

Жаргон — сразу расшифровывай простыми словами.\
"""

_ACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text", "time", "kind", "count_target"],
    "properties": {
        "text": {"type": "string"},
        "time": {"type": "string"},
        "kind": {"type": "string", "enum": ["once", "repeat", "project"]},
        "count_target": {"type": ["integer", "null"]},
    },
}

STAGE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tasks"],
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "steps"],
                "properties": {
                    "title": {"type": "string"},
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["title", "actions"],
                            "properties": {
                                "title": {"type": "string"},
                                "actions": {"type": "array", "items": _ACTION_SCHEMA},
                            },
                        },
                    },
                },
            },
        },
    },
}

STAGE_RETRY_HINT = {
    "role": "user",
    "content": (
        "Твой предыдущий ответ нарушил структуру. Исправь строго:\n"
        "- у каждой задачи минимум 1 шаг, у каждого шага минимум 1 действие;\n"
        "- у каждого действия есть непустой text и time; kind ∈ "
        "{once, repeat, project}; при kind=repeat задан целый count_target > 0;\n"
        "- никаких запрещённых формулировок (репетитор, платные курсы, НИШ/РФМШ, "
        "переезд, стажировка, бренды курсов/книг/платформ).\n"
        "Желательно: хотя бы одно действие kind=repeat со счётчиком в этапе.\n"
        "Верни раскрытие этапа заново по схеме."
    ),
}


# ─── Message builders ────────────────────────────────────────────────────────
# Keep prompts lean — the org's TPM budget is small and phase 2 fires several
# calls. Send only what each phase actually reasons over.
_FACT_KEYS = (
    "program_name", "university_name", "city", "country", "exams",
    "exam_hint_from_notes", "application_deadline", "language_level",
    "portfolio_needed", "required_documents", "min_ent_threshold",
    "admission_scores_2026", "notes", "grants", "is_foreign", "foreign_route",
    "language_exam",
)


def _compact_facts(facts: dict) -> dict:
    out = {k: facts.get(k) for k in _FACT_KEYS if facts.get(k) not in (None, [], {})}
    return out


def _full_student(sc) -> dict:
    """Phase 1 needs the whole picture for target/growth synthesis, but the
    matched-careers list is heavy and irrelevant here — trim it."""
    d = sc.model_dump()
    d["careers"] = [
        {"name": c.get("name"), "holland_code": c.get("holland_code")}
        for c in (d.get("careers") or [])[:3]
    ]
    return d


def _compact_student(sc) -> dict:
    """Phase 2 only personalizes wording — a short profile is enough."""
    return {
        "имя": sc.name,
        "класс": sc.grade,
        "город": sc.city,
        "любимые_предметы": sc.subjects_liked,
        "трудные_предметы": sc.subjects_hard,
        "нелюбимые_предметы": sc.subjects_disliked,
        "сильные_буквы_RIASEC": sc.strengths,
        "слабые_буквы_RIASEC": sc.weaknesses,
        "черты_характера": sc.personality_notes,
        "стиль_мышления": sc.thinking_style,
        "что_драйвит": sc.motivation_highlights,
    }


def _system(base: str, gi) -> str:
    text = base.format(
        grade=gi.grade,
        city=gi.city,
        university=gi.university_name,
        specialty=gi.specialty,
        tracks=", ".join(TRACKS),
        archetypes="; ".join(PROFESSION_ARCHETYPES),
    )
    if gi.is_foreign:
        text += _FOREIGN_BLOCK.format(
            language_exam=gi.language_exam or "IELTS / TOEFL",
            foreign_route=gi.foreign_route
            or "после 11 классов РК на английский бакалавриат напрямую обычно "
            "нельзя — нужен подготовительный год (foundation), либо "
            "международные экзамены (A-levels / IB), либо год в местном вузе",
        )
    return text


def build_skeleton_messages(gi) -> list[dict[str, str]]:
    slots = [{"slot": s, "label": l} for s, l in gi.stage_slots]
    user = "\n\n".join(
        [
            f"УЧЕНИК (всё, что мы о нём знаем):\n"
            f"{json.dumps(_full_student(gi.student_context), ensure_ascii=False, indent=2)}",
            f"ФАКТЫ ПО ВУЗУ (проверенные, не придумывай ничего сверх этого):\n"
            f"{json.dumps(_compact_facts(gi.admission_facts), ensure_ascii=False, indent=2)}",
            f"ЭТАПЫ (slot и label, ровно 4):\n{json.dumps(slots, ensure_ascii=False, indent=2)}",
            f"ПРЕДМЕТЫ, НУЖНЫЕ ПРОГРАММЕ: {', '.join(gi.subjects_needed) or '—'}",
            "Построй СКЕЛЕТ плана развития по схеме.",
        ]
    )
    return [
        {"role": "system", "content": _system(_SKELETON_SYSTEM, gi)},
        {"role": "user", "content": user},
    ]


def build_stage_messages(gi, stage: dict) -> list[dict[str, str]]:
    tasks_brief = [
        {"track": t["track"], "title": t["title"], "why": t["why"], "done_when": t["done_when"]}
        for t in stage["tasks"]
    ]
    sections = [
        f"ЭТАП: {stage['label']} (slot={stage['slot']}). Итог этапа: {stage['outcome']}",
        f"ЗАДАЧИ ЭТАПА:\n{json.dumps(tasks_brief, ensure_ascii=False, indent=2)}",
        f"УЧЕНИК (кратко для персонализации):\n"
        f"{json.dumps(_compact_student(gi.student_context), ensure_ascii=False, indent=2)}",
    ]
    if gi.curriculum_slices and any(t["track"] == "ent" for t in stage["tasks"]):
        anchors = {
            subj: sl.get("anchor_examples", [])
            for subj, sl in gi.curriculum_slices.items()
        }
        sections.append(
            "ПРИМЕРЫ ТЕМ-ЯКОРЕЙ (ранние классы) по профильным предметам — назови "
            "2-3 в кавычках как иллюстрацию к «проверь базу снизу вверх», НЕ строй "
            "план из списка тем:\n"
            f"{json.dumps(anchors, ensure_ascii=False, indent=2)}"
        )
    if any(t["track"] in ("admission", "language") for t in stage["tasks"]):
        sections.append(
            "ФАКТЫ ПО ВУЗУ (только это, ничего сверх):\n"
            f"{json.dumps(_compact_facts(gi.admission_facts), ensure_ascii=False, indent=2)}"
        )
    sections.append("Раскрой каждую задачу этапа в steps[] → actions[] по схеме.")
    return [
        {"role": "system", "content": _system(_STAGE_SYSTEM, gi)},
        {"role": "user", "content": "\n\n".join(sections)},
    ]
