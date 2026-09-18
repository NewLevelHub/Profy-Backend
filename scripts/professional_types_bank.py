"""PRO-338 Ф1.1 — full content for «Профессиональные типы» (ДДО Климова +
Йовайши/Резапкина): 20 forced-choice "интересы" pairs (instrument
`professional_types`, QuestionPair-based) + 5 Likert "способности" items
(instrument `professional_types_abilities`, Question-based). Source:
Тикеты-новые-тесты/02-Фаза1-Лёгкие-тесты.md §1.А Ф1.1 ("не заблокировано —
весь контент уже полон в спецификации").

Pattern 1:1 with riasec_question_bank.py/lie_scale_bank.py: this file is
pure content data, no DB access — scripts/seed_professional_types_questions.py
does the seeding.

Scale keys are Latin, not Cyrillic, in code (Ф1.2's own explicit
instruction) — `practical` (Ч-П), `technical` (Ч-Т), `social` (Ч-Ч), `sign`
(Ч-З), `artistic` (Ч-Х). No scoring service reads `scale` yet (no model
column for it — see PAIRS' own docstring below) — Ф1.2 (backend scoring:
1 point per pick + hybrid-profile flag) adds that when it implements
scoring; this bank only carries text/order/age_tier for now, matching the
Ф0.8 scope decision (2026-09-15) applied consistently here.
"""

# ── Kazakh (kk) — PRO-338 Ф4.4, translated+proofread in
# Тикеты-новые-тесты/kk-translations.md §1.4 (native-speaker review
# 2026-09-16). Keyed by ru text, folded into QUESTIONS/PAIRS below — same
# convention as eysenck_bank.py's `_KK_TEXT`.
_KK_ABILITIES_TEXT: dict[str, str] = {
    (
        "Способность к овладению различной техникой, умение охотно и "
        "подолгу что-нибудь мастерить, способность легко разбираться в "
        "технических чертежах и схемах"
    ): "Әртүрлі техниканы меңгеру қабілеті, бір нәрсені ықыласпен әрі ұзақ жасай білу дағдысы, техникалық сызбалар мен схемаларды еркін түсіну қабілеті",
    (
        "Умение логически мыслить, анализировать и обобщать различную "
        "информацию в виде цифр, знаков, текстов, способность ясно "
        "излагать мысли в письменной форме"
    ): "Логикалық ойлау, сандар, белгілер, мәтіндер түріндегі әртүрлі ақпаратты талдау және жинақтау білігі, ойды жазбаша түрде анық жеткізе білу қабілеті",
    (
        "Способность увидеть в обычном необычное, умение нестандартно "
        "мыслить, готовность подолгу заниматься рисованием или музыкой"
    ): "Кәдімгі нәрседен ерекшелік көре білу қабілеті, стандартты емес ойлау дағдысы, сурет салумен немесе музыкамен ұзақ уақыт айналысуға дайын болу",
    (
        "Умение устанавливать взаимоотношения с окружающими, способность "
        "вызывать симпатию, умение улаживать разногласия и находить "
        "компромиссы"
    ): "Айналасындағылармен қарым-қатынас орната білу, өзіне деген жанашырлық тудыра білу қабілеті, келіспеушіліктерді реттеп, ымыраға келе білу дағдысы",
    (
        "Наблюдательность за живой природой, выносливость при работе в "
        "полевых условиях"
    ): "Тірі табиғатты бақылағыштық, далалық жағдайда жұмыс істеу кезіндегі төзімділік",
}


def _abilities_text(ru: str) -> dict[str, str]:
    return {"ru": ru, "kk": _KK_ABILITIES_TEXT[ru]}


# ─── Способности (Likert 0-3) — instrument=professional_types_abilities ────
# order 400-404 — right after MI (267-314) in the "Дополнительные тесты"
# contiguous block (see scripts/eysenck_bank.py / scripts/elers_bank.py for
# the rest of that block, order 410-510).
QUESTIONS: list[dict] = [
    {
        "order": 400,
        "scale": "technical",
        "text": _abilities_text(
            "Способность к овладению различной техникой, умение охотно и "
            "подолгу что-нибудь мастерить, способность легко разбираться в "
            "технических чертежах и схемах"
        ),
        "age_tier": "senior",
    },
    {
        "order": 401,
        "scale": "sign",
        "text": _abilities_text(
            "Умение логически мыслить, анализировать и обобщать различную "
            "информацию в виде цифр, знаков, текстов, способность ясно "
            "излагать мысли в письменной форме"
        ),
        "age_tier": "senior",
    },
    {
        "order": 402,
        "scale": "artistic",
        "text": _abilities_text(
            "Способность увидеть в обычном необычное, умение нестандартно "
            "мыслить, готовность подолгу заниматься рисованием или музыкой"
        ),
        "age_tier": "senior",
    },
    {
        "order": 403,
        "scale": "social",
        "text": _abilities_text(
            "Умение устанавливать взаимоотношения с окружающими, способность "
            "вызывать симпатию, умение улаживать разногласия и находить "
            "компромиссы"
        ),
        "age_tier": "senior",
    },
    {
        "order": 404,
        "scale": "practical",
        "text": _abilities_text(
            "Наблюдательность за живой природой, выносливость при работе в "
            "полевых условиях"
        ),
        "age_tier": "senior",
    },
]

# ─── Интересы (20 forced-choice pairs) — instrument=professional_types ─────
# Each pair's two options are DEDICATED new Question rows (unlike
# question_pairing.py's junior/middle pairs, which reuse existing riasec/
# big_five content) — ДДО's activities aren't shared with any other
# instrument. `scale` on each option is the Ф1.2 scoring key (1 point to
# that scale when picked) — not read by any code yet, same "content+order
# only" scope as QUESTIONS above.
#
# order 340-379 (40 rows, 2 per pair, consecutive) — placed before
# QUESTIONS' own 400-404 so the whole "test 1" content (pairs + abilities)
# sits in one readable range, even though `question_pair_service.get_pairs`
# always renders pairs after every plain Likert item regardless of `order`
# (see buildDisplaySequence.ts) — `order` here only matters for stable
# per-row identity (the seed script's upsert key) and `display_order`
# (min of the two options' `order`, used to sort pairs among themselves).
#
# age_tier "senior" only — matches QUESTIONS above and the rest of the
# "Дополнительные тесты" block (epic's "14-18 only" note); `get_pairs`
# checks `QuestionPair.age_tier == age_group` (exact match, not cumulative
# like Question.age_tier), so middle/junior never see these.
#
# pair_index starts at 68, NOT 1 — question_pair_service.submit_pair_answers
# resolves a submitted answer via `QuestionPair.pair_index.in_(...)` with NO
# instrument/age_tier filter, so pair_index must be unique across the WHOLE
# question_pairs table, not just within this instrument. question_pairing.py
# already occupies 1-67 (one shared running counter across junior/middle
# riasec+big_five) — continuing at 68 avoids colliding with an existing
# riasec/big_five pair and getting the wrong one resolved on submit.
PAIRS: list[dict] = [
    {
        "pair_index": 68,
        "option_a": {"order": 340, "text": "Ухаживать за животными", "scale": "practical"},
        "option_b": {"order": 341, "text": "Обслуживать машины, приборы", "scale": "technical"},
    },
    {
        "pair_index": 69,
        "option_a": {"order": 342, "text": "Помогать больным людям", "scale": "social"},
        "option_b": {
            "order": 343,
            "text": "Составлять таблицы, схемы, программы вычислительных машин",
            "scale": "sign",
        },
    },
    {
        "pair_index": 70,
        "option_a": {
            "order": 344,
            "text": "Следить за качеством книжных иллюстраций, плакатов",
            "scale": "artistic",
        },
        "option_b": {"order": 345, "text": "Следить за состоянием, развитием растений", "scale": "practical"},
    },
    {
        "pair_index": 71,
        "option_a": {"order": 346, "text": "Обрабатывать материалы (дерево, ткань, металл)", "scale": "technical"},
        "option_b": {"order": 347, "text": "Доводить товары до потребителя", "scale": "social"},
    },
    {
        "pair_index": 72,
        "option_a": {"order": 348, "text": "Обсуждать научно-популярные книги, статьи", "scale": "sign"},
        "option_b": {
            "order": 349,
            "text": "Обсуждать художественные книги (или пьесы, концерты)",
            "scale": "artistic",
        },
    },
    {
        "pair_index": 73,
        "option_a": {"order": 350, "text": "Выращивать молодняк (животных какой-либо породы)", "scale": "practical"},
        "option_b": {
            "order": 351,
            "text": "Тренировать товарищей (или младших) в выполнении действий",
            "scale": "social",
        },
    },
    {
        "pair_index": 74,
        "option_a": {
            "order": 352,
            "text": "Копировать рисунки, изображения, настраивать инструменты",
            "scale": "artistic",
        },
        "option_b": {"order": 353, "text": "Управлять подъемным краном, трактором, тепловозом", "scale": "technical"},
    },
    {
        "pair_index": 75,
        "option_a": {
            "order": 354,
            "text": "Сообщать, разъяснять людям необходимые им сведения",
            "scale": "social",
        },
        "option_b": {"order": 355, "text": "Оформлять выставки, витрины", "scale": "artistic"},
    },
    {
        "pair_index": 76,
        "option_a": {"order": 356, "text": "Ремонтировать вещи, изделия, технику", "scale": "technical"},
        "option_b": {
            "order": 357,
            "text": "Искать и исправлять ошибки в текстах, таблицах, рисунках",
            "scale": "sign",
        },
    },
    {
        "pair_index": 77,
        "option_a": {"order": 358, "text": "Лечить животных", "scale": "practical"},
        "option_b": {"order": 359, "text": "Выполнять вычисления, расчеты", "scale": "sign"},
    },
    {
        "pair_index": 78,
        "option_a": {"order": 360, "text": "Выводить новые сорта растений", "scale": "practical"},
        "option_b": {
            "order": 361,
            "text": "Конструировать, проектировать новые промышленные изделия",
            "scale": "technical",
        },
    },
    {
        "pair_index": 79,
        "option_a": {
            "order": 362,
            "text": "Разбирать споры, ссоры между людьми, убеждать, поощрять",
            "scale": "social",
        },
        "option_b": {"order": 363, "text": "Разбираться в чертежах, схемах, графиках", "scale": "sign"},
    },
    {
        "pair_index": 80,
        "option_a": {
            "order": 364,
            "text": "Участвовать в работе кружков художественной самодеятельности",
            "scale": "artistic",
        },
        "option_b": {"order": 365, "text": "Наблюдать, изучать жизнь микробов", "scale": "practical"},
    },
    {
        "pair_index": 81,
        "option_a": {
            "order": 366,
            "text": "Обслуживать, налаживать медицинские приборы и аппараты",
            "scale": "technical",
        },
        "option_b": {
            "order": 367,
            "text": "Оказывать людям медицинскую помощь при ранениях, болезнях",
            "scale": "social",
        },
    },
    {
        "pair_index": 82,
        "option_a": {
            "order": 368,
            "text": "Составлять точные описания, отчеты о наблюдаемых явлениях",
            "scale": "artistic",
        },
        "option_b": {"order": 369, "text": "Художественно описывать, изображать события", "scale": "sign"},
    },
    {
        "pair_index": 83,
        "option_a": {"order": 370, "text": "Делать лабораторные анализы в больнице", "scale": "practical"},
        "option_b": {"order": 371, "text": "Принимать, осматривать больных", "scale": "social"},
    },
    {
        "pair_index": 84,
        "option_a": {
            "order": 372,
            "text": "Красить или расписывать стены помещений, поверхность изделий",
            "scale": "artistic",
        },
        "option_b": {"order": 373, "text": "Осуществлять монтаж зданий или сборку машин", "scale": "technical"},
    },
    {
        "pair_index": 85,
        "option_a": {
            "order": 374,
            "text": "Организовывать культпоходы сверстников или младших в театры",
            "scale": "social",
        },
        "option_b": {"order": 375, "text": "Играть на сцене", "scale": "artistic"},
    },
    {
        "pair_index": 86,
        "option_a": {
            "order": 376,
            "text": "Изготовлять по чертежам детали, изделия, строить здания",
            "scale": "technical",
        },
        "option_b": {"order": 377, "text": "Заниматься черчением, копировать чертежи, карты", "scale": "sign"},
    },
    {
        "pair_index": 87,
        "option_a": {
            "order": 378,
            "text": "Вести борьбу с болезнями растений, с вредителями леса",
            "scale": "practical",
        },
        "option_b": {"order": 379, "text": "Работать на клавишных аппаратах (пишущей машинке, телетайпе)", "scale": "sign"},
    },
]

# Kazakh (kk) for the 40 pair-option texts (20 pairs × 2), same source/
# review as `_KK_ABILITIES_TEXT` above — Тикеты-новые-тесты/
# kk-translations.md §1.3.
_KK_PAIR_TEXT: dict[str, str] = {
    "Ухаживать за животными": "Жануарларды күту",
    "Обслуживать машины, приборы": "Машиналар мен құрылғыларға қызмет көрсету",
    "Помогать больным людям": "Науқас адамдарға көмектесу",
    "Составлять таблицы, схемы, программы вычислительных машин": "Кестелер, схемалар, есептеуіш машиналарға арналған бағдарламалар құрастыру",
    "Следить за качеством книжных иллюстраций, плакатов": "Кітап иллюстрацияларының, плакаттардың сапасын қадағалау",
    "Следить за состоянием, развитием растений": "Өсімдіктердің жай-күйін, дамуын қадағалау",
    "Обрабатывать материалы (дерево, ткань, металл)": "Материалдарды (ағаш, мата, металл) өңдеу",
    "Доводить товары до потребителя": "Тауарларды тұтынушыға жеткізу",
    "Обсуждать научно-популярные книги, статьи": "Ғылыми-көпшілік кітаптарды, мақалаларды талқылау",
    "Обсуждать художественные книги (или пьесы, концерты)": "Көркем әдебиетті (немесе пьесаларды, концерттерді) талқылау",
    "Выращивать молодняк (животных какой-либо породы)": "Жас төлді (белгілі бір тұқымды жануарларды) өсіру",
    "Тренировать товарищей (или младших) в выполнении действий": "Құрдастарды (немесе кішілерді) әрекеттерді орындауға баулу",
    "Копировать рисунки, изображения, настраивать инструменты": "Суреттерді, бейнелерді көшіру, құралдарды баптау",
    "Управлять подъемным краном, трактором, тепловозом": "Көтергіш кранды, тракторды, тепловозды басқару",
    "Сообщать, разъяснять людям необходимые им сведения": "Адамдарға қажетті мәліметтерді хабарлау, түсіндіру",
    "Оформлять выставки, витрины": "Көрмелерді, витриналарды безендіру",
    "Ремонтировать вещи, изделия, технику": "Заттарды, бұйымдарды, техниканы жөндеу",
    "Искать и исправлять ошибки в текстах, таблицах, рисунках": "Мәтіндердегі, кестелердегі, суреттердегі қателерді іздеу және түзету",
    "Лечить животных": "Жануарларды емдеу",
    "Выполнять вычисления, расчеты": "Есептеулер жүргізу",
    "Выводить новые сорта растений": "Өсімдіктердің жаңа сорттарын шығару",
    "Конструировать, проектировать новые промышленные изделия": "Жаңа өнеркәсіптік бұйымдарды құрастыру, жобалау",
    "Разбирать споры, ссоры между людьми, убеждать, поощрять": "Адамдар арасындағы дау-жанжалды шешу, сендіру, көтермелеу",
    "Разбираться в чертежах, схемах, графиках": "Сызбаларды, схемаларды, графиктерді түсіну",
    "Участвовать в работе кружков художественной самодеятельности": "Көркемөнерпаздар үйірмесінің жұмысына қатысу",
    "Наблюдать, изучать жизнь микробов": "Микробтардың тіршілігін бақылау, зерттеу",
    "Обслуживать, налаживать медицинские приборы и аппараты": "Медициналық құралдар мен аппараттарға қызмет көрсету, баптау",
    "Оказывать людям медицинскую помощь при ранениях, болезнях": "Жарақат, аурулар кезінде адамдарға медициналық көмек көрсету",
    "Составлять точные описания, отчеты о наблюдаемых явлениях": "Бақыланатын құбылыстар туралы дәл сипаттамалар, есептер құрастыру",
    "Художественно описывать, изображать события": "Оқиғаларды көркем сипаттау, бейнелеу",
    "Делать лабораторные анализы в больнице": "Ауруханада зертханалық талдаулар жасау",
    "Принимать, осматривать больных": "Науқастарды қабылдау, қарау",
    "Красить или расписывать стены помещений, поверхность изделий": "Үй-жайлардың қабырғаларын, бұйымдардың бетін бояу немесе әшекейлеу",
    "Осуществлять монтаж зданий или сборку машин": "Ғимараттарды монтаждау немесе машиналарды жинау",
    "Организовывать культпоходы сверстников или младших в театры": "Құрдастардың немесе кішілердің театрға мәдени сапарын ұйымдастыру",
    "Играть на сцене": "Сахнада ойнау",
    "Изготовлять по чертежам детали, изделия, строить здания": "Сызбалар бойынша бөлшектер, бұйымдар жасау, ғимарат салу",
    "Заниматься черчением, копировать чертежи, карты": "Сызу ісімен айналысу, сызбаларды, карталарды көшіру",
    "Вести борьбу с болезнями растений, с вредителями леса": "Өсімдік ауруларымен, орман зиянкестерімен күресу",
    "Работать на клавишных аппаратах (пишущей машинке, телетайпе)": "Пернетақталы аппараттарда (жазу машинкасы, телетайп) жұмыс істеу",
}

for _pair in PAIRS:
    for _opt_key in ("option_a", "option_b"):
        _opt = _pair[_opt_key]
        _opt["text"] = {"ru": _opt["text"], "kk": _KK_PAIR_TEXT[_opt["text"]]}

_ru_pair_texts = {
    opt["text"]["ru"] for pair in PAIRS for opt in (pair["option_a"], pair["option_b"])
}
assert set(_KK_PAIR_TEXT) == _ru_pair_texts, (
    f"_KK_PAIR_TEXT drift: missing={sorted(_ru_pair_texts - set(_KK_PAIR_TEXT))}, "
    f"stray={sorted(set(_KK_PAIR_TEXT) - _ru_pair_texts)}"
)

assert len(PAIRS) == 20, f"ДДО must have exactly 20 pairs, got {len(PAIRS)}"
_pair_orders = [p["option_a"]["order"] for p in PAIRS] + [p["option_b"]["order"] for p in PAIRS]
assert len(_pair_orders) == len(set(_pair_orders)), "pair option orders must be unique"

# Instruction shown once, above the whole pairs block (not per-pair framing
# like junior/middle's scenarios) — Ф1.3 (Report + FE) wires this into the
# actual screen; kept here as the content of record.
INSTRUCTION = {
    "ru": (
        "Предположим, что после соответствующего обучения Вы сможете выполнить "
        "любую работу. Из предложенных 20 пар видов деятельности в каждой паре "
        "выберите только один вид, который для Вас предпочтительнее."
    ),
    "kk": (
        "Тиісті оқудан кейін кез келген жұмысты орындай алатыныңызды "
        "елестетіп көріңіз. Ұсынылған 20 жұп қызмет түрінің әрқайсысынан "
        "өзіңізге қолайлырақ бір түрді ғана таңдаңыз."
    ),
}
