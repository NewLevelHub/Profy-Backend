"""PRO-338 Ф3.2 — full content bank for АСТУР ("Характеристики интеллекта").

Subtest 8, «Геометрические фигуры» (Ф3.1), is now included — its 5 items
and their letter key (А/Б/В/Г) were supplied directly by a psychologist,
not derived from `Спецификации психологических тестов.docx` like subtests
1-7. Unlike every other subtest, GEOMETRIC_FIGURES_ITEMS below carries NO
content beyond `answer`: the stimulus is a static image asset
(Profy-Frontend's `public/astur-figures/`, cropped and recolored from the
psychologist's own scanned stimulus sheet — a hand-authored SVG-path
redraw was tried first and didn't faithfully reproduce the real shapes),
addressed by the item's 1-based position, never by server-sent geometry.
It is
**deliberately NOT wired into `astur_scoring.py`'s `_SCORERS`/
`MAX_RAW_SCORE` yet** — that total is pinned 1:1 to `astur_thresholds.json`'s
SPN-group cut-offs (Ф3.5), and folding in a new subtest's points without
recalibrating those cut-offs would silently shift every existing threshold.
Content here is submitted/stored like any other subtest (`is_complete()`
already requires it); only its contribution to `raw_score`/`spn_group`
awaits that calibration pass.

Source for subtests 1-7: `Спецификации психологических тестов.docx`,
section «Блок «Характеристики интеллекта»» → «3. Полный список вопросов и
варианты ответов». That section's own header is explicit: **"официальный
банк заданий АСТУР (методическое руководство 1995 года) в открытом доступе
не найден... раздел 3 — рабочий черновик v1, составленный заново по формату
и духу методики... формулировки, сложность и ключи должны быть проверены и
откалиброваны психологом перед выводом теста в продакшн."** This bank is a
faithful, unmodified transcription of that draft — not an attempt to
"fix" or improve it; content calibration is explicitly out of scope here
and belongs to a psychologist review pass before production use.

103 items total = 95 scored-or-scorable (20+16+12+19+8+15+5, across 7
subtests currently marked `scored`) + 8 lability commands (own table,
explicitly excluded from the total score per the spec, see Ф3.5). Of
those 95, only 90 (subtests 1-2/4-7) currently feed `raw_score` — see the
geometric_figures note above.

Like Belbin (Ф2.2), АСТУР is NOT Question-model content — Ф0.2 gave it no
QuestionInstrument member (its own table `astur_runs` lands in Ф3.3), so
this module is imported directly wherever it's needed, not resynced via a
seed script.
"""

# 3 subject-area tags used by "Осведомлённость" and "Обобщение" items only
# (Ф3.5's "профиль обучения" is computed from exactly these two subtests).
SUBJECTS: dict[str, str] = {
    "humanities": "Гуманитарный",
    "physics_math": "Физико-математический",
    "natural_science": "Естественнонаучный",
}

# Fixed instruction text per subtest, verbatim from the spec (Ф3.2 ticket).
SUBTESTS: list[dict] = [
    {
        "key": "awareness",
        "name": "Осведомлённость",
        "instruction": "Прочитайте предложение, в котором пропущено слово. Выберите из пяти вариантов слово, которое подходит по смыслу.",
        "item_count": 20,
        "scored": True,
    },
    {
        "key": "analogies",
        "name": "Двойные аналогии",
        "instruction": "Даны два слова в известном отношении друг к другу и третье слово. Подберите слово, которое относится к третьему так же, как второе относится к первому.",
        "item_count": 16,
        "scored": True,
    },
    {
        "key": "lability",
        "name": "Понимание инструкций (лабильность)",
        "instruction": "Как можно быстрее выполните то, что говорится в задании.",
        "item_count": 8,
        # Ф3.5: scored separately (first-half vs second-half accuracy),
        # never added to the overall intelligence score.
        "scored": False,
    },
    {
        "key": "classification",
        "name": "Классификации",
        "instruction": "В каждой строке шесть слов. Найдите ровно два слова, которые связаны между собой общим признаком.",
        "item_count": 12,
        "scored": True,
    },
    {
        "key": "generalization",
        "name": "Обобщение",
        "instruction": "Даны два понятия. Впишите одно слово или короткое словосочетание, которое их обобщает.",
        "item_count": 19,
        "scored": True,
    },
    {
        "key": "logical_schemas",
        "name": "Логические схемы",
        "instruction": "Расставьте понятия по порядку — от самого общего к самому частному — и соедините их стрелками.",
        "item_count": 8,
        "scored": True,
    },
    {
        "key": "numeric_series",
        "name": "Числовые ряды",
        "instruction": "Каждый ряд чисел построен по своему правилу. Определите правило и впишите два числа, которые продолжают ряд.",
        "item_count": 15,
        "scored": True,
    },
    {
        "key": "geometric_figures",
        "name": "Геометрические фигуры",
        "instruction": "Определите, из каких частей (А, Б, В или Г) можно без пропусков и остатка собрать фигуру-эталон слева.",
        "item_count": 5,
        # Tracked like any other subtest (submit/is_complete) — see this
        # module's docstring for why it's not yet in astur_scoring.py's
        # raw_score total.
        "scored": True,
    },
]

# 1-based subtest number (matches the spec's own "Субтест N" numbering and
# `POST /assessment/{id}/astur/subtest/{n}`, Ф3.4) -> that subtest's
# metadata dict from SUBTESTS above. geometric_figures (Ф3.1) is number 8.
SUBTEST_BY_NUMBER: dict[int, dict] = {i + 1: s for i, s in enumerate(SUBTESTS)}


# --- Субтест 1. Осведомлённость (20, MC 5 вариантов а-д -> options list) ---
# Each item: text with a blank, 5 options (4 for none here), the correct
# option's exact text as `answer` (not an index/letter — the option text
# itself is the unambiguous, self-documenting key), and a subject tag.
AWARENESS_ITEMS: list[dict] = [
    {"text": "Одинаковыми по смыслу являются слова «биография» и …?",
     "options": ["случай", "подвиг", "жизнеописание", "книга", "писатель"],
     "answer": "жизнеописание", "subject": "humanities"},
    {"text": "Слово, противоположное по смыслу слову «дефицит», — это …?",
     "options": ["нехватка", "избыток", "недостаток", "потеря", "расход"],
     "answer": "избыток", "subject": "humanities"},
    {"text": "Наука, изучающая строение и жизнедеятельность клетки, называется …?",
     "options": ["генетика", "цитология", "экология", "анатомия", "физиология"],
     "answer": "цитология", "subject": "natural_science"},
    {"text": "Раздел математики, изучающий фигуры на плоскости и в пространстве, — это …?",
     "options": ["алгебра", "геометрия", "арифметика", "статистика", "тригонометрия"],
     "answer": "геометрия", "subject": "physics_math"},
    {"text": "Человек, который пишет музыку, называется …?",
     "options": ["дирижёр", "исполнитель", "композитор", "аранжировщик", "солист"],
     "answer": "композитор", "subject": "humanities"},
    {"text": "Слово, близкое по значению слову «монарх», — это …?",
     "options": ["президент", "министр", "правитель", "депутат", "судья"],
     "answer": "правитель", "subject": "humanities"},
    {"text": "Наименьшая структурная единица живого организма — это …?",
     "options": ["молекула", "атом", "клетка", "ткань", "орган"],
     "answer": "клетка", "subject": "natural_science"},
    {"text": "Раздел физики, изучающий движение тел, называется …?",
     "options": ["оптика", "механика", "термодинамика", "электричество", "акустика"],
     "answer": "механика", "subject": "physics_math"},
    {"text": "«Метафора» — это …?",
     "options": ["точное определение", "скрытое сравнение", "вопрос без ответа", "повторение звуков", "список фактов"],
     "answer": "скрытое сравнение", "subject": "humanities"},
    {"text": "Прибор для измерения температуры — это …?",
     "options": ["барометр", "термометр", "амперметр", "манометр", "спидометр"],
     "answer": "термометр", "subject": "physics_math"},
    {"text": "Слово, противоположное по смыслу слову «централизация», — это …?",
     "options": ["объединение", "децентрализация", "концентрация", "унификация", "интеграция"],
     "answer": "децентрализация", "subject": "humanities"},
    {"text": "Совокупность правил поведения, принятых в обществе и не закреплённых законом, называется …?",
     "options": ["закон", "мораль", "устав", "кодекс", "регламент"],
     "answer": "мораль", "subject": "humanities"},
    {"text": "Наука о языке называется …?",
     "options": ["лингвистика", "философия", "социология", "психология", "риторика"],
     "answer": "лингвистика", "subject": "humanities"},
    {"text": "Единица измерения силы электрического тока — это …?",
     "options": ["вольт", "ватт", "ампер", "ом", "джоуль"],
     "answer": "ампер", "subject": "physics_math"},
    {"text": "Слово, близкое по значению слову «эволюция», — это …?",
     "options": ["революция", "развитие", "застой", "кризис", "регресс"],
     "answer": "развитие", "subject": "natural_science"},
    {"text": "Раздел биологии, изучающий наследственность, называется …?",
     "options": ["экология", "генетика", "анатомия", "физиология", "микробиология"],
     "answer": "генетика", "subject": "natural_science"},
    {"text": "«Ирония» — это …?",
     "options": ["прямое высказывание", "скрытая насмешка", "громкий крик", "точный расчёт", "искреннее восхищение"],
     "answer": "скрытая насмешка", "subject": "humanities"},
    {"text": "Совокупность гор, вытянутых в одну систему, называется …?",
     "options": ["равнина", "хребет", "плато", "низменность", "впадина"],
     "answer": "хребет", "subject": "natural_science"},
    {"text": "Наука об обществе и общественных отношениях называется …?",
     "options": ["экономика", "социология", "политология", "история", "философия"],
     "answer": "социология", "subject": "humanities"},
    {"text": "Единица измерения количества вещества в химии — это …?",
     "options": ["грамм", "литр", "моль", "градус", "паскаль"],
     "answer": "моль", "subject": "natural_science"},
]


# --- Субтест 2. Двойные аналогии (16, MC 5 вариантов; item 4 has only 4 in
# the source — preserved as-is, not padded with an invented 5th option) ---
ANALOGIES_ITEMS: list[dict] = [
    {"pair": ("лес", "деревья"), "third": "библиотека",
     "options": ["сад", "двор", "город", "театр", "книги"], "answer": "книги"},
    {"pair": ("бежать", "кричать"), "third": "стоять",
     "options": ["молчать", "ползать", "шуметь", "звать", "плакать"], "answer": "молчать"},
    {"pair": ("огурец", "овощ"), "third": "георгин",
     "options": ["сорняк", "роса", "садик", "цветок", "земля"], "answer": "цветок"},
    {"pair": ("учитель", "ученик"), "third": "врач",
     "options": ["койка", "больные", "палата", "термометр"], "answer": "больные"},
    {"pair": ("огород", "морковь"), "third": "сад",
     "options": ["забор", "яблоня", "колодец", "скамейка", "цветы"], "answer": "яблоня"},
    {"pair": ("цветок", "ваза"), "third": "птица",
     "options": ["клюв", "чайка", "гнездо", "яйцо", "перья"], "answer": "гнездо"},
    {"pair": ("писатель", "книга"), "third": "художник",
     "options": ["кисть", "картина", "холст", "краска", "музей"], "answer": "картина"},
    {"pair": ("зима", "снег"), "third": "лето",
     "options": ["дождь", "жара", "отпуск", "море", "загар"], "answer": "жара"},
    {"pair": ("слово", "предложение"), "third": "кирпич",
     "options": ["глина", "дом", "стена", "стройка", "раствор"], "answer": "дом"},
    {"pair": ("река", "берег"), "third": "море",
     "options": ["волна", "побережье", "корабль", "рыба", "глубина"], "answer": "побережье"},
    {"pair": ("голод", "еда"), "third": "жажда",
     "options": ["стакан", "вода", "колодец", "жара", "пить"], "answer": "вода"},
    {"pair": ("семя", "растение"), "third": "яйцо",
     "options": ["гнездо", "скорлупа", "птица", "курица", "желток"], "answer": "птица"},
    {"pair": ("урок", "учитель"), "third": "концерт",
     "options": ["билет", "зал", "музыкант", "афиша", "сцена"], "answer": "музыкант"},
    {"pair": ("холод", "лёд"), "third": "жар",
     "options": ["огонь", "пар", "зной", "костёр", "жара"], "answer": "пар"},
    {"pair": ("глаз", "зрение"), "third": "ухо",
     "options": ["звук", "слух", "музыка", "шум", "тишина"], "answer": "слух"},
    {"pair": ("завод", "рабочий"), "third": "поле",
     "options": ["трактор", "урожай", "крестьянин", "земля", "зерно"], "answer": "крестьянин"},
]


# --- Субтест 3. Понимание инструкций / лабильность (8 команд) ---
# Each command has its OWN answer format (цифра/фигура/слово/символ) and a
# short per-item time limit (Ф3.4's job, not content — no timer value here).
# Two commands (2 and 6) are deliberately self-referential/date-dependent —
# a legitimate, common lability-test technique (it tests whether the
# respondent can quickly apply a rule to real-time context, not just static
# facts) — so they have NO fixed `answer`; instead `dynamic` names what the
# future scoring service (Ф3.5) must resolve at grading time:
#   "day_of_week" -> the actual weekday of `submitted_at`
#   "own_name"    -> the respondent's own first/last name (profile)
# Every other command's answer is fully static and computed once here.
LABILITY_ITEMS: list[dict] = [
    {"instruction": "Если после слова «стол» по алфавиту идёт слово «стул» — напишите цифру 1, если нет — цифру 2.",
     "answer_format": "digit", "answer": "1"},
    {"instruction": "Обведите кружок, если сегодняшний день недели начинается с согласной буквы, иначе — обведите квадрат.",
     "answer_format": "shape", "dynamic": "day_of_week"},
    {"instruction": "Если 7 больше 5 — поставьте плюс, если нет — поставьте минус.",
     "answer_format": "symbol", "answer": "плюс"},
    {"instruction": "Зачеркните чётное число из пары «3 и 8», иначе зачеркните нечётное.",
     "answer_format": "digit", "answer": "8"},
    {"instruction": "Если слово «зима» ближе по смыслу к слову «снег», чем к слову «жара», — напишите «да», иначе — «нет».",
     "answer_format": "word", "answer": "да"},
    {"instruction": "Подчеркните первую букву своего имени, если она гласная, иначе — подчеркните последнюю букву фамилии.",
     "answer_format": "letter", "dynamic": "own_name"},
    {"instruction": "Если месяц май идёт раньше месяца март — поставьте галочку, иначе — крестик.",
     "answer_format": "symbol", "answer": "крестик"},
    {"instruction": "Напишите слово «выше», если 10 больше 100, иначе напишите слово «ниже».",
     "answer_format": "word", "answer": "ниже"},
]


# --- Субтест 4. Классификации (12, выбор 2 слов из 6) ---
# `note` is documentary only (the shared feature the 2 key words have in
# common) — never part of scoring, which only checks the 2-word `answer`.
CLASSIFICATION_ITEMS: list[dict] = [
    {"words": ["дог", "стол", "книга", "спаниель", "окно", "дерево"],
     "answer": ["дог", "спаниель"], "note": "породы собак"},
    {"words": ["скрипка", "чашка", "гитара", "тарелка", "ложка", "дверь"],
     "answer": ["скрипка", "гитара"], "note": "струнные музыкальные инструменты"},
    {"words": ["дуб", "роза", "шкаф", "сосна", "диван", "экран"],
     "answer": ["дуб", "сосна"], "note": "деревья"},
    {"words": ["тигр", "книга", "лев", "ручка", "стол", "окно"],
     "answer": ["тигр", "лев"], "note": "крупные кошки-хищники"},
    {"words": ["роза", "тюльпан", "стол", "стул", "окно", "дверь"],
     "answer": ["роза", "тюльпан"], "note": "садовые цветы"},
    {"words": ["арбуз", "дыня", "картофель", "зеркало", "лампа", "диван"],
     "answer": ["арбуз", "дыня"], "note": "бахчевые культуры"},
    {"words": ["волк", "лиса", "корова", "лампа", "зеркало", "диван"],
     "answer": ["волк", "лиса"], "note": "дикие хищники семейства псовых"},
    {"words": ["гитара", "барабан", "стол", "стул", "лампа", "зеркало"],
     "answer": ["гитара", "барабан"], "note": "музыкальные инструменты"},
    {"words": ["пшеница", "рожь", "шкаф", "стол", "чашка", "стул"],
     "answer": ["пшеница", "рожь"], "note": "зерновые культуры"},
    {"words": ["трамвай", "троллейбус", "яблоко", "груша", "стол", "книга"],
     "answer": ["трамвай", "троллейбус"], "note": "электротранспорт"},
    {"words": ["орёл", "сокол", "курица", "корова", "стол", "книга"],
     "answer": ["орёл", "сокол"], "note": "хищные птицы"},
    {"words": ["клён", "берёза", "стол", "книга", "чашка", "зеркало"],
     "answer": ["клён", "берёза"], "note": "лиственные деревья"},
]


# --- Субтест 5. Обобщение (19 пар, открытый ответ, 0/1/2 балла) ---
# `score_2`/`score_1` are lists of acceptable synonym/near-formulations
# (Ф3.5: "нормализованное сравнение [...] с эталонным списком", not exact
# string match) — comma-separated alternatives in the source become
# separate list entries. `score_0_example` is documentary only (an
# illustrative wrong answer for the spec/report, never matched against).
GENERALIZATION_ITEMS: list[dict] = [
    {"pair": ("Ель", "сосна"), "score_2": ["хвойные деревья"],
     "score_1": ["деревья", "растения", "лес"],
     "score_0_example": "растут в лесу, из них делают мебель", "subject": "natural_science"},
    {"pair": ("Сказка", "былина"), "score_2": ["устное народное творчество", "фольклор"],
     "score_1": ["литература", "творчество"],
     "score_0_example": "предание, выдумка, легенда", "subject": "humanities"},
    {"pair": ("Атом", "молекула"), "score_2": ["мельчайшие частицы вещества"],
     "score_1": ["частица", "вещество"],
     "score_0_example": "состав клетки", "subject": "physics_math"},
    {"pair": ("Ботаника", "зоология"), "score_2": ["биология", "наука о живой природе"],
     "score_1": ["наука", "предмет", "дисциплина"],
     "score_0_example": "природа, животные и растения", "subject": "natural_science"},
    {"pair": ("Живопись", "скульптура"), "score_2": ["изобразительное искусство"],
     "score_1": ["искусство", "творчество", "культура"],
     "score_0_example": "картины, фрески", "subject": "humanities"},
    {"pair": ("Африка", "Антарктида"), "score_2": ["части света", "материки"],
     "score_1": ["географические объекты", "суша"],
     "score_0_example": "страны, климат", "subject": "natural_science"},
    {"pair": ("Ампер", "Вольт"), "score_2": ["единицы измерения электрических величин"],
     "score_1": ["физические величины", "электричество"],
     "score_0_example": "единица, прибор", "subject": "physics_math"},
    {"pair": ("Сердце", "артерия"), "score_2": ["органы кровеносной системы"],
     "score_1": ["внутренние органы человека"],
     "score_0_example": "биология, сосуды", "subject": "natural_science"},
    {"pair": ("Париж", "Лондон"), "score_2": ["столицы государств"],
     "score_1": ["города", "населённые пункты"],
     "score_0_example": "страны, Европа", "subject": "humanities"},
    {"pair": ("Феодализм", "капитализм"), "score_2": ["общественно-экономические формации"],
     "score_1": ["общество", "эпохи", "ступени развития"],
     "score_0_example": "классы, история", "subject": "humanities"},
    {"pair": ("Смелость", "доброта"), "score_2": ["положительные черты характера"],
     "score_1": ["качества", "свойства личности"],
     "score_0_example": "сила, эмоции", "subject": "humanities"},
    {"pair": ("Водохранилище", "канал"), "score_2": ["искусственные водные сооружения"],
     "score_1": ["сооружение", "водоём"],
     "score_0_example": "вода, строение", "subject": "physics_math"},
    {"pair": ("Сумма", "произведение"), "score_2": ["результаты математических действий"],
     "score_1": ["математические операции"],
     "score_0_example": "математика, цифры", "subject": "physics_math"},
    {"pair": ("Наука", "искусство"), "score_2": ["виды человеческой деятельности"],
     "score_1": ["творчество", "познание"],
     "score_0_example": "знание, просвещение", "subject": "humanities"},
    {"pair": ("Белок", "жир"), "score_2": ["органические вещества"],
     "score_1": ["состав вещества", "нутриенты"],
     "score_0_example": "витамины, углеводы", "subject": "natural_science"},
    {"pair": ("Газ", "жидкость"), "score_2": ["агрегатные состояния вещества"],
     "score_1": ["вещество", "состояние тела"],
     "score_0_example": "физика, вода и воздух", "subject": "physics_math"},
    {"pair": ("Землетрясение", "смерч"), "score_2": ["стихийные бедствия"],
     "score_1": ["явления природы"],
     "score_0_example": "разрушение, опасность", "subject": "natural_science"},
    {"pair": ("Метафора", "аллегория"), "score_2": ["художественные приёмы", "средства выразительности"],
     "score_1": ["способы изложения"],
     "score_0_example": "сравнение, рассказ", "subject": "humanities"},
    {"pair": ("Классицизм", "романтизм"), "score_2": ["направления в искусстве"],
     "score_1": ["литературные направления", "эпохи"],
     "score_0_example": "литература", "subject": "humanities"},
]


# --- Субтест 6. Логические схемы (8 иерархических цепочек) ---
# `concepts` is the CORRECT order, general -> specific — shuffling for the
# drag-and-drop UI is a frontend/runtime concern, not content. Score = 1
# point per correctly restored adjacent link (len(concepts) - 1 max).
LOGICAL_SCHEMA_ITEMS: list[dict] = [
    {"concepts": ["живое существо", "животное", "млекопитающее", "кошка", "сиамская кошка"]},
    {"concepts": ["государство", "область", "город", "улица", "дом"]},
    {"concepts": ["искусство", "литература", "поэзия", "сонет"]},
    {"concepts": ["число", "натуральное число", "чётное число", "24"]},
    {"concepts": ["транспорт", "наземный транспорт", "рельсовый транспорт", "трамвай"]},
    {"concepts": ["вещество", "органическое вещество", "белок", "фермент"]},
    {"concepts": ["учебное заведение", "школа", "старшие классы", "11 класс"]},
    {"concepts": ["наука", "естественная наука", "биология", "генетика"]},
]


# --- Субтест 7. Числовые ряды (15, открытый числовой ввод x2) ---
# `rule` is documentary only (helps a specialist/content reviewer, never
# part of scoring, which only checks `answer` — both numbers must match).
NUMERIC_SERIES_ITEMS: list[dict] = [
    {"sequence": [2, 4, 6, 8, 10, 12], "answer": [14, 16], "rule": "шаг +2"},
    {"sequence": [1, 2, 4, 8, 16], "answer": [32, 64], "rule": "умножение на 2"},
    {"sequence": [3, 6, 9, 12, 15], "answer": [18, 21], "rule": "шаг +3"},
    {"sequence": [1, 4, 9, 16, 25], "answer": [36, 49], "rule": "квадраты натуральных чисел"},
    {"sequence": [100, 90, 80, 70], "answer": [60, 50], "rule": "шаг -10"},
    {"sequence": [1, 1, 2, 3, 5, 8], "answer": [13, 21], "rule": "сумма двух предыдущих чисел"},
    {"sequence": [5, 10, 20, 40], "answer": [80, 160], "rule": "умножение на 2"},
    {"sequence": [2, 3, 5, 8, 12], "answer": [17, 23], "rule": "разница увеличивается на 1"},
    {"sequence": [243, 81, 27, 9], "answer": [3, 1], "rule": "деление на 3"},
    {"sequence": [1, 3, 6, 10, 15], "answer": [21, 28], "rule": "разница увеличивается на 1"},
    {"sequence": [20, 17, 14, 11], "answer": [8, 5], "rule": "шаг -3"},
    {"sequence": [2, 6, 18, 54], "answer": [162, 486], "rule": "умножение на 3"},
    {"sequence": [7, 14, 21, 28], "answer": [35, 42], "rule": "шаг +7"},
    {"sequence": [1, 2, 6, 24], "answer": [120, 720], "rule": "умножение на возрастающее число (x2,x3,x4,x5,x6)"},
    {"sequence": [64, 32, 16, 8], "answer": [4, 2], "rule": "деление на 2"},
]


# --- Субтест 8. Геометрические фигуры (5, MC 4 варианта а-г) ---
# No geometry lives here — unlike every other subtest, the stimulus is a
# static image asset (Profy-Frontend's `public/astur-figures/{n}-{target|
# a|b|v|g}.png`, n = 1-based item position), generated by cropping and
# recoloring the actual source stimulus sheet (5 scanned figures the
# psychologist supplied — see git history for the extraction script) rather
# than hand-authored SVG paths: an earlier hand-drawn-path attempt here
# didn't faithfully reproduce the real stimulus shapes, so this now stores
# only what the server actually owns — the answer key — and the frontend
# addresses images by item position, no content needed on the wire (see
# `astur_service._PUBLIC_ITEM_FIELDS["geometric_figures"]` = `()`).
GEOMETRIC_FIGURES_ITEMS: list[dict] = [
    {"answer": "Г"},
    {"answer": "Б"},
    {"answer": "Г"},
    {"answer": "Б"},
    {"answer": "В"},
]


# subtest key -> its item list, for callers that look a subtest up by
# SUBTEST_BY_NUMBER[n]["key"] and need the actual items (structural
# validation of a submit payload, Ф3.4 — never used for scoring, Ф3.5).
SUBTEST_ITEMS: dict[str, list[dict]] = {
    "awareness": AWARENESS_ITEMS,
    "analogies": ANALOGIES_ITEMS,
    "lability": LABILITY_ITEMS,
    "classification": CLASSIFICATION_ITEMS,
    "generalization": GENERALIZATION_ITEMS,
    "logical_schemas": LOGICAL_SCHEMA_ITEMS,
    "numeric_series": NUMERIC_SERIES_ITEMS,
    "geometric_figures": GEOMETRIC_FIGURES_ITEMS,
}


# --- Self-checks: shape/count invariants, run once at import time ---

_EXPECTED_COUNTS = {
    "awareness": (AWARENESS_ITEMS, 20),
    "analogies": (ANALOGIES_ITEMS, 16),
    "lability": (LABILITY_ITEMS, 8),
    "classification": (CLASSIFICATION_ITEMS, 12),
    "generalization": (GENERALIZATION_ITEMS, 19),
    "logical_schemas": (LOGICAL_SCHEMA_ITEMS, 8),
    "numeric_series": (NUMERIC_SERIES_ITEMS, 15),
    "geometric_figures": (GEOMETRIC_FIGURES_ITEMS, 5),
}

for _key, (_items, _expected) in _EXPECTED_COUNTS.items():
    assert len(_items) == _expected, f"{_key} must have exactly {_expected} items, got {len(_items)}"
    assert next(s["item_count"] for s in SUBTESTS if s["key"] == _key) == _expected

_TOTAL_ITEMS = sum(count for _, count in _EXPECTED_COUNTS.values())
assert _TOTAL_ITEMS == 103, f"АСТУР (8 subtests) must total 103 items, got {_TOTAL_ITEMS}"

_SCORED_TOTAL = sum(count for key, (_, count) in _EXPECTED_COUNTS.items() if key != "lability")
assert _SCORED_TOTAL == 95, f"scored-or-scorable items (excluding lability) must total 95, got {_SCORED_TOTAL}"

for _item in AWARENESS_ITEMS:
    assert 4 <= len(_item["options"]) <= 5
    assert _item["answer"] in _item["options"]
    assert _item["subject"] in SUBJECTS

for _item in ANALOGIES_ITEMS:
    assert 4 <= len(_item["options"]) <= 5
    assert _item["answer"] in _item["options"]

for _item in LABILITY_ITEMS:
    assert ("answer" in _item) != ("dynamic" in _item), (
        "each lability item is either fully static (answer) or dynamic "
        "(needs submission-time context) — never both, never neither"
    )

for _item in CLASSIFICATION_ITEMS:
    assert len(_item["words"]) == 6
    assert len(_item["answer"]) == 2
    assert set(_item["answer"]).issubset(set(_item["words"]))

for _item in GENERALIZATION_ITEMS:
    assert _item["score_2"] and _item["score_1"]
    assert _item["subject"] in SUBJECTS
    # A phrase must not appear in both tiers — ambiguous scoring otherwise.
    assert not set(_item["score_2"]) & set(_item["score_1"])

for _item in LOGICAL_SCHEMA_ITEMS:
    assert len(_item["concepts"]) >= 3

for _item in NUMERIC_SERIES_ITEMS:
    assert len(_item["answer"]) == 2

_FIGURE_LETTERS = {"А", "Б", "В", "Г"}
for _item in GEOMETRIC_FIGURES_ITEMS:
    assert _item["answer"] in _FIGURE_LETTERS

assert set(SUBTEST_BY_NUMBER.keys()) == {1, 2, 3, 4, 5, 6, 7, 8}
assert set(SUBTEST_ITEMS.keys()) == {s["key"] for s in SUBTESTS}
for _n, _meta in SUBTEST_BY_NUMBER.items():
    assert len(SUBTEST_ITEMS[_meta["key"]]) == _meta["item_count"]
