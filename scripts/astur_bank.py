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
# `{ru,kk}` — PRO-338 Ф4.4, Тикеты-новые-тесты/kk-translations.md §6.9
# (native-speaker review 2026-09-18).
SUBJECTS: dict[str, dict[str, str]] = {
    "humanities": {"ru": "Гуманитарный", "kk": "Гуманитарлық"},
    "physics_math": {"ru": "Физико-математический", "kk": "Физика-математикалық"},
    "natural_science": {"ru": "Естественнонаучный", "kk": "Жаратылыстану"},
}

# Fixed instruction text per subtest, verbatim from the spec (Ф3.2 ticket).
# `name`/`instruction` — `{ru,kk}` dicts, PRO-338 Ф4.4, kk translated in
# Тикеты-новые-тесты/kk-translations.md §6.1/§7.6 (native-speaker review
# 2026-09-18). Subtest names have no official Kazakh АСТУР adaptation to
# match (see kk-translations.md §6's own note) — first terminological choice.
SUBTESTS: list[dict] = [
    {
        "key": "awareness",
        "name": {"ru": "Осведомлённость", "kk": "Хабардарлық"},
        "instruction": {
            "ru": "Прочитайте предложение, в котором пропущено слово. Выберите из пяти вариантов слово, которое подходит по смыслу.",
            "kk": "Бір сөзі түсіп қалған сөйлемді оқыңыз. Ұсынылған бес нұсқадан мағынасына сай келетін сөзді таңдаңыз.",
        },
        "item_count": 20,
        "scored": True,
    },
    {
        "key": "analogies",
        "name": {"ru": "Двойные аналогии", "kk": "Қос аналогия"},
        "instruction": {
            "ru": "Даны два слова в известном отношении друг к другу и третье слово. Подберите слово, которое относится к третьему так же, как второе относится к первому.",
            "kk": "Бір-бірімен белгілі қатынаста тұрған екі сөз және үшінші сөз берілген. Екінші сөз біріншіге қалай қатысты болса, үшінші сөзге дәл солай қатысты болатын сөзді таңдаңыз.",
        },
        "item_count": 16,
        "scored": True,
    },
    {
        "key": "lability",
        "name": {"ru": "Понимание инструкций (лабильность)", "kk": "Нұсқауларды түсіну (лабильділік)"},
        "instruction": {
            "ru": "Как можно быстрее выполните то, что говорится в задании.",
            "kk": "Тапсырмада айтылғанды мүмкіндігінше тез орындаңыз.",
        },
        "item_count": 8,
        # Ф3.5: scored separately (first-half vs second-half accuracy),
        # never added to the overall intelligence score.
        "scored": False,
    },
    {
        "key": "classification",
        "name": {"ru": "Классификации", "kk": "Жіктеу"},
        "instruction": {
            "ru": "В каждой строке шесть слов. Найдите ровно два слова, которые связаны между собой общим признаком.",
            "kk": "Әр жолда алты сөз бар. Ортақ белгісімен байланысқан дәл екі сөзді табыңыз.",
        },
        "item_count": 12,
        "scored": True,
    },
    {
        "key": "generalization",
        "name": {"ru": "Обобщение", "kk": "Жалпылау"},
        "instruction": {
            "ru": "Даны два понятия. Впишите одно слово или короткое словосочетание, которое их обобщает.",
            "kk": "Екі ұғым берілген. Оларды жалпылайтын бір сөз немесе қысқа тіркес жазыңыз.",
        },
        "item_count": 19,
        "scored": True,
    },
    {
        "key": "logical_schemas",
        "name": {"ru": "Логические схемы", "kk": "Логикалық схемалар"},
        "instruction": {
            "ru": "Расставьте понятия по порядку — от самого общего к самому частному — и соедините их стрелками.",
            "kk": "Ұғымдарды реттілікпен орналастырыңыз — ең жалпыдан ең жекеге қарай — және оларды көрсеткілермен қосыңыз.",
        },
        "item_count": 8,
        "scored": True,
    },
    {
        "key": "numeric_series",
        "name": {"ru": "Числовые ряды", "kk": "Сандар қатары"},
        "instruction": {
            "ru": "Каждый ряд чисел построен по своему правилу. Определите правило и впишите два числа, которые продолжают ряд.",
            "kk": "Әр сандар қатары өз ережесі бойынша құрылған. Ережені анықтап, қатарды жалғастыратын екі санды жазыңыз.",
        },
        "item_count": 15,
        "scored": True,
    },
    {
        "key": "geometric_figures",
        "name": {"ru": "Геометрические фигуры", "kk": "Геометриялық фигуралар"},
        "instruction": {
            "ru": "Определите, из каких частей (А, Б, В или Г) можно без пропусков и остатка собрать фигуру-эталон слева.",
            "kk": "Сол жақтағы эталон фигураны қандай бөліктерден (А, Б, В немесе Г) қалдықсыз және бос орынсыз құрастыруға болатынын анықтаңыз.",
        },
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
#   "own_name"    -> whether the respondent's own first name starts with a
#                    vowel (see astur_scoring._own_name_expected_answer)
# Every other command's answer is fully static and computed once here.
#
# `options` (added 2026-09-18): every item's answer space was ALREADY a
# closed set of exactly 2 possible values — the frontend just wasn't told
# that, so every non-shape item rendered as a free-text box under a 20s
# timer, which live in-office testing showed was genuinely hard to use (had
# to read the instruction, work out the answer, AND type it correctly, all
# under time pressure). `options` lets LabilityRunner render two buttons
# instead, same as item 2 already did for its shape answer. Item 6 was
# additionally reworded (see below) so it also reduces to a plain yes/no
# instead of "identify and type a specific Cyrillic letter derived from a
# 2-branch rule about your own name" — that compound task was the hardest
# item in the whole subtest even for an adult test-taker, per direct
# feedback, and diluted the point of a *speed* subtest into a spelling test.
LABILITY_ITEMS: list[dict] = [
    {"instruction": "Если после слова «стол» по алфавиту идёт слово «стул» — напишите цифру 1, если нет — цифру 2.",
     "answer_format": "digit", "answer": "1", "options": ["1", "2"]},
    {"instruction": "Обведите кружок, если сегодняшний день недели начинается с согласной буквы, иначе — обведите квадрат.",
     "answer_format": "shape", "dynamic": "day_of_week", "options": ["кружок", "квадрат"]},
    {"instruction": "Если 7 больше 5 — поставьте плюс, если нет — поставьте минус.",
     "answer_format": "symbol", "answer": "плюс", "options": ["плюс", "минус"]},
    {"instruction": "Из пары чисел «3 и 8» напишите то число, которое является чётным.",
     "answer_format": "digit", "answer": "8", "options": ["3", "8"]},
    {"instruction": "Если слово «зима» ближе по смыслу к слову «снег», чем к слову «жара», — напишите «да», иначе — «нет».",
     "answer_format": "word", "answer": "да", "options": ["да", "нет"]},
    {"instruction": "Первая буква вашего имени — гласная? Выберите «Да» или «Нет».",
     "answer_format": "word", "dynamic": "own_name", "options": ["да", "нет"]},
    {"instruction": "Если месяц май идёт раньше месяца март — поставьте галочку, иначе — крестик.",
     "answer_format": "symbol", "answer": "крестик", "options": ["галочка", "крестик"]},
    {"instruction": "Напишите слово «выше», если 10 больше 100, иначе напишите слово «ниже».",
     "answer_format": "word", "answer": "ниже", "options": ["выше", "ниже"]},
]


# --- Субтест 4. Классификации (12, выбор 2 слов из 6) ---
# `note` is documentary only (the shared feature the 2 key words have in
# common) — never part of scoring, which only checks the 2-word `answer`.
CLASSIFICATION_ITEMS: list[dict] = [
    {"words": ["собака", "стол", "книга", "спаниель", "окно", "дерево"],
     "answer": ["собака", "спаниель"], "note": "породы собак/виды"},
    {"words": ["скрипка", "чашка", "гитара", "тарелка", "ложка", "дверь"],
     "answer": ["скрипка", "гитара"], "note": "струнные музыкальные инструменты"},
    {"words": ["дуб", "роза", "шкаф", "сосна", "будильник", "экран"],
     "answer": ["дуб", "сосна"], "note": "деревья"},
    {"words": ["тигр", "книга", "лев", "ручка", "стол", "окно"],
     "answer": ["тигр", "лев"], "note": "крупные кошки-хищники"},
    {"words": ["роза", "тюльпан", "стол", "шарф", "будильник", "дверь"],
     "answer": ["роза", "тюльпан"], "note": "садовые цветы"},
    {"words": ["арбуз", "дыня", "будильник", "зеркало", "лампа", "диван"],
     "answer": ["арбуз", "дыня"], "note": "бахчевые культуры"},
    {"words": ["волк", "лиса", "корова", "лампа", "зеркало", "диван"],
     "answer": ["волк", "лиса"], "note": "дикие хищники семейства псовых"},
    {"words": ["гитара", "барабан", "стол", "часы", "тетрадь", "зеркало"],
     "answer": ["гитара", "барабан"], "note": "музыкальные инструменты"},
    {"words": ["пшеница", "рожь", "шкаф", "зонт", "чашка", "будильник"],
     "answer": ["пшеница", "рожь"], "note": "зерновые культуры"},
    {"words": ["трамвай", "троллейбус", "полотенце", "книга", "будильник", "зеркало"],
     "answer": ["трамвай", "троллейбус"], "note": "электротранспорт"},
    {"words": ["орёл", "сокол", "курица", "зонт", "стол", "книга"],
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
    {"pair": ("Ель", "сосна"), "score_2": ["хвойные деревья", "хвойные породы деревьев", "хвойные растения", "хвойные"],
     "score_1": ["деревья", "растения", "лес", "флора"],
     "score_0_example": "растут в лесу, из них делают мебель", "subject": "natural_science"},
    {"pair": ("Сказка", "былина"), "score_2": ["устное народное творчество", "фольклор", "народное творчество"],
     "score_1": ["литература", "творчество", "жанры литературы", "произведения"],
     "score_0_example": "предание, выдумка, легенда", "subject": "humanities"},
    {"pair": ("Атом", "молекула"), "score_2": ["мельчайшие частицы вещества", "частицы вещества", "микрочастицы"],
     "score_1": ["частица", "вещество", "материя"],
     "score_0_example": "состав клетки", "subject": "physics_math"},
    {"pair": ("Ботаника", "зоология"), "score_2": ["биология", "наука о живой природе", "науки о природе"],
     "score_1": ["наука", "предмет", "дисциплина", "школьный предмет"],
     "score_0_example": "природа, животные и растения", "subject": "natural_science"},
    {"pair": ("Живопись", "скульптура"), "score_2": ["изобразительное искусство", "виды изобразительного искусства"],
     "score_1": ["искусство", "творчество", "культура", "виды искусства"],
     "score_0_example": "картины, фрески", "subject": "humanities"},
    {"pair": ("Африка", "Антарктида"), "score_2": ["части света", "материки", "континенты"],
     "score_1": ["географические объекты", "суша", "земли"],
     "score_0_example": "страны, климат", "subject": "natural_science"},
    {"pair": ("Ампер", "Вольт"), "score_2": ["единицы измерения электрических величин", "единицы измерения электричества", "электрические единицы измерения"],
     "score_1": ["физические величины", "электричество", "единицы измерения"],
     "score_0_example": "единица, прибор", "subject": "physics_math"},
    {"pair": ("Сердце", "артерия"), "score_2": ["органы кровеносной системы", "органы системы кровообращения", "части кровеносной системы"],
     "score_1": ["внутренние органы человека", "органы человека", "органы"],
     "score_0_example": "биология, сосуды", "subject": "natural_science"},
    {"pair": ("Париж", "Лондон"), "score_2": ["столицы государств", "столицы стран", "европейские столицы"],
     "score_1": ["города", "населённые пункты", "крупные города"],
     "score_0_example": "страны, Европа", "subject": "humanities"},
    {"pair": ("Феодализм", "капитализм"), "score_2": ["общественно-экономические формации", "экономические формации", "исторические формации"],
     "score_1": ["общество", "эпохи", "ступени развития", "периоды истории"],
     "score_0_example": "классы, история", "subject": "humanities"},
    {"pair": ("Смелость", "доброта"), "score_2": ["положительные черты характера", "положительные качества характера", "хорошие черты характера"],
     "score_1": ["качества", "свойства личности", "черты характера"],
     "score_0_example": "сила, эмоции", "subject": "humanities"},
    {"pair": ("Водохранилище", "канал"), "score_2": ["искусственные водные сооружения", "гидротехнические сооружения", "искусственные водоёмы"],
     "score_1": ["сооружение", "водоём", "водные объекты"],
     "score_0_example": "вода, строение", "subject": "physics_math"},
    {"pair": ("Сумма", "произведение"), "score_2": ["результаты математических действий", "результаты арифметических действий", "результаты вычислений"],
     "score_1": ["математические операции", "арифметические действия", "действия с числами"],
     "score_0_example": "математика, цифры", "subject": "physics_math"},
    {"pair": ("Наука", "искусство"), "score_2": ["виды человеческой деятельности", "формы человеческой деятельности", "сферы деятельности человека"],
     "score_1": ["творчество", "познание", "деятельность"],
     "score_0_example": "знание, просвещение", "subject": "humanities"},
    {"pair": ("Белок", "жир"), "score_2": ["органические вещества", "органические соединения"],
     "score_1": ["состав вещества", "нутриенты", "питательные вещества"],
     "score_0_example": "витамины, углеводы", "subject": "natural_science"},
    {"pair": ("Газ", "жидкость"), "score_2": ["агрегатные состояния вещества", "состояния вещества"],
     "score_1": ["вещество", "состояние тела", "физические состояния"],
     "score_0_example": "физика, вода и воздух", "subject": "physics_math"},
    {"pair": ("Землетрясение", "смерч"), "score_2": ["стихийные бедствия", "природные катастрофы", "стихийные явления"],
     "score_1": ["явления природы", "природные явления"],
     "score_0_example": "разрушение, опасность", "subject": "natural_science"},
    {"pair": ("Метафора", "аллегория"), "score_2": ["художественные приёмы", "средства выразительности", "изобразительно-выразительные средства"],
     "score_1": ["способы изложения", "литературные приёмы", "приёмы"],
     "score_0_example": "сравнение, рассказ", "subject": "humanities"},
    {"pair": ("Классицизм", "романтизм"), "score_2": ["направления в искусстве", "художественные направления", "литературные течения"],
     "score_1": ["литературные направления", "эпохи", "стили"],
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


# ── Kazakh (kk) — PRO-338 Ф4.4 ──────────────────────────────────────────────
# `Тикеты-новые-тесты/kk-translations.md` §6 (native-speaker review
# 2026-09-18, subtests 1-2 flagged there for extra lexical scrutiny — see
# that section's own warning about synonym/antonym relations not always
# surviving translation). Positional lists (index i = item i+1), not
# key-fold dicts like the Likert banks — these items are compound
# (text+options, pair+third+options, ...) so a single ru-string key isn't
# enough to address "the options of this item" unambiguously. NUMERIC_SERIES
# (pure numbers) and GEOMETRIC_FIGURES (a letter key, stimulus is an image
# asset) need no kk content at all — see their own sections in
# kk-translations.md §6.8/module docstring above.

_KK_AWARENESS: list[dict] = [
    {"text": "«Өмірбаян» сөзімен мағынасы жақын сөз — бұл …?", "options": ["оқиға", "ерлік", "өмірбаяндық сипаттама", "кітап", "жазушы"]},
    {"text": "«Тапшылық» сөзіне мағынасы қарама-қарсы сөз — бұл …?", "options": ["жетіспеушілік", "молшылық", "кемшілік", "жоғалту", "шығын"]},
    {"text": "Жасушаның құрылысы мен тіршілік әрекетін зерттейтін ғылым — бұл …?", "options": ["генетика", "цитология", "экология", "анатомия", "физиология"]},
    {"text": "Жазықтықтағы және кеңістіктегі фигураларды зерттейтін математика саласы — бұл …?", "options": ["алгебра", "геометрия", "арифметика", "статистика", "тригонометрия"]},
    {"text": "Музыка жазатын адам — бұл …?", "options": ["дирижёр", "орындаушы", "композитор", "аранжировщик", "солист"]},
    {"text": "«Монарх» сөзіне мағынасы жақын сөз — бұл …?", "options": ["президент", "министр", "билеуші", "депутат", "судья"]},
    {"text": "Тірі ағзаның ең кіші құрылымдық бірлігі — бұл …?", "options": ["молекула", "атом", "жасуша", "тін", "мүше"]},
    {"text": "Денелердің қозғалысын зерттейтін физика саласы — бұл …?", "options": ["оптика", "механика", "термодинамика", "электр", "акустика"]},
    {"text": "«Метафора» дегеніміз — бұл …?", "options": ["нақты анықтама", "жасырын салыстыру", "жауапсыз сұрақ", "дыбыстардың қайталануы", "фактілер тізімі"]},
    {"text": "Температураны өлшеуге арналған құрал — бұл …?", "options": ["барометр", "термометр", "амперметр", "манометр", "спидометр"]},
    {"text": "«Орталықтандыру» сөзіне қарама-қарсы мағыналы сөз — бұл …?", "options": ["біріктіру", "орталықсыздандыру", "шоғырландыру", "біркелкілендіру", "интеграция"]},
    {"text": "Қоғамда қабылданған, бірақ заңмен бекітілмеген мінез-құлық ережелерінің жиынтығы — бұл …?", "options": ["заң", "имандылық", "жарғы", "кодекс", "регламент"]},
    {"text": "Тіл туралы ғылым — бұл …?", "options": ["лингвистика", "философия", "социология", "психология", "риторика"]},
    {"text": "Электр тогының күшін өлшеу бірлігі — бұл …?", "options": ["вольт", "ватт", "ампер", "ом", "джоуль"]},
    {"text": "«Эволюция» сөзіне мағынасы жақын сөз — бұл …?", "options": ["революция", "даму", "тоқырау", "дағдарыс", "регресс"]},
    {"text": "Тұқым қуалаушылықты зерттейтін биология саласы — бұл …?", "options": ["экология", "генетика", "анатомия", "физиология", "микробиология"]},
    {"text": "«Ирония» дегеніміз — бұл …?", "options": ["тікелей айтылған ой", "жасырын мысқыл", "қатты айқай", "дәл есеп", "шынайы тамсану"]},
    {"text": "Бір жүйеге созылған таулардың жиынтығы — бұл …?", "options": ["жазық", "жота", "үстірт", "ойпат", "ойыс"]},
    {"text": "Қоғам және қоғамдық қатынастар туралы ғылым — бұл …?", "options": ["экономика", "әлеуметтану", "саясаттану", "тарих", "философия"]},
    {"text": "Химияда зат мөлшерін өлшеу бірлігі — бұл …?", "options": ["грамм", "литр", "моль", "градус", "паскаль"]},
]
assert len(_KK_AWARENESS) == len(AWARENESS_ITEMS)

for _ru, _kk in zip(AWARENESS_ITEMS, _KK_AWARENESS, strict=True):
    assert len(_ru["options"]) == len(_kk["options"]), _ru["text"]
    _kk_answer = _kk["options"][_ru["options"].index(_ru["answer"])]
    _ru["text"] = {"ru": _ru["text"], "kk": _kk["text"]}
    _ru["options"] = {"ru": _ru["options"], "kk": _kk["options"]}
    _ru["answer"] = {"ru": _ru["answer"], "kk": _kk_answer}


_KK_ANALOGIES: list[dict] = [
    {"pair": ("орман", "ағаштар"), "third": "кітапхана", "options": ["бақ", "аула", "қала", "театр", "кітаптар"]},
    {"pair": ("жүгіру", "айқайлау"), "third": "тұру", "options": ["үндемеу", "еңбектеу", "шуылдау", "шақыру", "жылау"]},
    {"pair": ("қиярша", "көкөніс"), "third": "георгин", "options": ["арам шөп", "шық", "бақша", "гүл", "жер"]},
    {"pair": ("мұғалім", "оқушы"), "third": "дәрігер", "options": ["төсек", "науқастар", "палата", "термометр"]},
    {"pair": ("бақша", "сәбіз"), "third": "бақ", "options": ["қоршау", "алма ағашы", "құдық", "орындық", "гүлдер"]},
    {"pair": ("гүл", "құмыра"), "third": "құс", "options": ["тұмсық", "шағала", "ұя", "жұмыртқа", "қауырсын"]},
    {"pair": ("жазушы", "кітап"), "third": "суретші", "options": ["қылқалам", "сурет", "кенеп", "бояу", "мұражай"]},
    {"pair": ("қыс", "қар"), "third": "жаз", "options": ["жаңбыр", "ыстық", "демалыс", "теңіз", "күнге күю"]},
    {"pair": ("сөз", "сөйлем"), "third": "кірпіш", "options": ["балшық", "үй", "қабырға", "құрылыс", "ерітінді"]},
    {"pair": ("өзен", "жағалау"), "third": "теңіз", "options": ["толқын", "жағалау аймағы", "кеме", "балық", "тереңдік"]},
    {"pair": ("аштық", "тамақ"), "third": "шөлдеу", "options": ["стакан", "су", "құдық", "ыстық", "ішу"]},
    {"pair": ("тұқым", "өсімдік"), "third": "жұмыртқа", "options": ["ұя", "қабықша", "құс", "тауық", "сарысы"]},
    {"pair": ("сабақ", "мұғалім"), "third": "концерт", "options": ["билет", "зал", "музыкант", "афиша", "сахна"]},
    {"pair": ("суық", "мұз"), "third": "ыстық", "options": ["от", "бу", "аптап", "алау", "ыстық"]},
    {"pair": ("көз", "көру"), "third": "құлақ", "options": ["дыбыс", "есту", "музыка", "шу", "тыныштық"]},
    {"pair": ("зауыт", "жұмысшы"), "third": "егістік", "options": ["трактор", "өнім", "шаруа", "жер", "дән"]},
]
assert len(_KK_ANALOGIES) == len(ANALOGIES_ITEMS)

for _ru, _kk in zip(ANALOGIES_ITEMS, _KK_ANALOGIES, strict=True):
    assert len(_ru["options"]) == len(_kk["options"]), _ru["pair"]
    _kk_answer = _kk["options"][_ru["options"].index(_ru["answer"])]
    _ru["pair"] = {"ru": list(_ru["pair"]), "kk": list(_kk["pair"])}
    _ru["third"] = {"ru": _ru["third"], "kk": _kk["third"]}
    _ru["options"] = {"ru": _ru["options"], "kk": _kk["options"]}
    _ru["answer"] = {"ru": _ru["answer"], "kk": _kk_answer}


_KK_LABILITY: list[dict] = [
    {"instruction": "Егер «стол» сөзінен кейін әліпби бойынша «стул» сөзі келсе — 1 санын жазыңыз, келмесе — 2 санын жазыңыз.", "options": ["1", "2"], "answer": "1"},
    {"instruction": "Егер бүгінгі апта күні дауыссыз дыбыстан басталса — шеңберді сызыңыз, олай болмаса — шаршыны сызыңыз.", "options": ["шеңбер", "шаршы"]},
    {"instruction": "Егер 7 саны 5-тен көп болса — қосу белгісін қойыңыз, олай болмаса — азайту белгісін қойыңыз.", "options": ["қосу", "азайту"], "answer": "қосу"},
    {"instruction": "«3 және 8» жұбынан жұп санды жазыңыз.", "options": ["3", "8"], "answer": "8"},
    {"instruction": "Егер «қыс» сөзі мағынасы жағынан «қар» сөзіне «ыстық» сөзінен гөрі жақынырақ болса — «иә» деп жазыңыз, олай болмаса — «жоқ» деп жазыңыз.", "options": ["иә", "жоқ"], "answer": "иә"},
    {"instruction": "Есіміңіздің бірінші әрпі дауысты дыбыс па? «Иә» немесе «Жоқ» деп таңдаңыз.", "options": ["иә", "жоқ"]},
    {"instruction": "Егер мамыр айы наурыз айынан бұрын келсе — құстырма белгісін қойыңыз, олай болмаса — айқас белгісін қойыңыз.", "options": ["құстырма", "айқас"], "answer": "айқас"},
    {"instruction": "Егер 10 саны 100-ден көп болса — «жоғары» деген сөзді жазыңыз, олай болмаса — «төмен» деген сөзді жазыңыз.", "options": ["жоғары", "төмен"], "answer": "төмен"},
]
assert len(_KK_LABILITY) == len(LABILITY_ITEMS)

for _ru, _kk in zip(LABILITY_ITEMS, _KK_LABILITY, strict=True):
    assert len(_ru["options"]) == len(_kk["options"]) == 2
    _ru["instruction"] = {"ru": _ru["instruction"], "kk": _kk["instruction"]}
    _ru["options"] = {"ru": _ru["options"], "kk": _kk["options"]}
    if "answer" in _ru:
        assert "answer" in _kk, _ru["instruction"]
        _ru["answer"] = {"ru": _ru["answer"], "kk": _kk["answer"]}


_KK_CLASSIFICATION: list[list[str]] = [
    ["ит", "үстел", "кітап", "спаниель", "терезе", "ағаш"],
    ["скрипка", "кесе", "гитара", "тәрелке", "қасық", "есік"],
    ["емен", "раушан", "шкаф", "қарағай", "диван", "экран"],
    ["жолбарыс", "кітап", "арыстан", "қалам", "үстел", "терезе"],
    ["раушан", "қызғалдақ", "үстел", "шарф", "оятқыш", "есік"],
    ["қарбыз", "қауын", "оятқыш", "айна", "шам", "диван"],
    ["қасқыр", "түлкі", "сиыр", "шам", "айна", "диван"],
    ["гитара", "барабан", "үстел", "сағат", "дәптер", "айна"],
    ["бидай", "қара бидай", "шкаф", "қолшатыр", "кесе", "оятқыш"],
    ["трамвай", "троллейбус", "сүлгі", "кітап", "оятқыш", "айна"],
    ["бүркіт", "сұңқар", "тауық", "қолшатыр", "үстел", "кітап"],
    ["үйеңкі", "қайың", "үстел", "кітап", "кесе", "айна"],
]
assert len(_KK_CLASSIFICATION) == len(CLASSIFICATION_ITEMS)

for _ru, _kk_words in zip(CLASSIFICATION_ITEMS, _KK_CLASSIFICATION, strict=True):
    assert len(_ru["words"]) == len(_kk_words) == 6
    _kk_answer = [_kk_words[_ru["words"].index(w)] for w in _ru["answer"]]
    _ru["words"] = {"ru": _ru["words"], "kk": _kk_words}
    _ru["answer"] = {"ru": _ru["answer"], "kk": _kk_answer}


# `score_2`/`score_1` are lists of acceptable phrasings (see
# GENERALIZATION_ITEMS' own docstring) — kk versions translated by meaning,
# not literally, same "natural generalization, not calque" approach the
# ru originals themselves use.
_KK_GENERALIZATION: list[dict] = [
    {"pair": ("Шырша", "қарағай"), "score_2": ["қылқан жапырақты ағаштар", "қылқан жапырақтылар", "қылқанжапырақтылар", "қылқан жапырақты"], "score_1": ["ағаштар", "өсімдіктер", "орман", "ағаш", "өсімдік"]},
    {"pair": ("Ертегі", "батырлар жыры"), "score_2": ["ауыз әдебиеті", "ауызша халық шығармашылығы", "фольклор", "халық шығармашылығы"], "score_1": ["әдебиет", "шығармашылық"]},
    {"pair": ("Атом", "молекула"), "score_2": ["заттың ең ұсақ бөлшектері", "ұсақ бөлшектер", "микробөлшектер"], "score_1": ["бөлшек", "зат", "бөлшектер"]},
    {"pair": ("Ботаника", "зоология"), "score_2": ["биология", "тірі табиғат туралы ғылым", "жаратылыстану ғылымы"], "score_1": ["ғылым", "пән", "ғылымдар", "пәндер"]},
    {"pair": ("Кескіндеме", "мүсін өнері"), "score_2": ["бейнелеу өнері", "бейнелеу өнерінің түрлері"], "score_1": ["өнер", "шығармашылық", "мәдениет", "өнер түрлері"]},
    {"pair": ("Африка", "Антарктида"), "score_2": ["әлем бөліктері", "материктер", "материк", "құрлық", "құрлықтар"], "score_1": ["географиялық объектілер", "құрлықтар мен аймақтар", "жер бедері"]},
    {"pair": ("Ампер", "Вольт"), "score_2": ["электр шамаларын өлшеу бірліктері", "өлшем бірліктері", "өлшем бірлігі", "өлшем бірлік"], "score_1": ["физикалық шамалар", "электр", "шамалар"]},
    {"pair": ("Жүрек", "артерия"), "score_2": ["қан айналым жүйесінің мүшелері", "қан айналымы", "қан айналым жүйесі"], "score_1": ["адамның ішкі мүшелері", "ішкі мүшелер", "мүшелер"]},
    {"pair": ("Париж", "Лондон"), "score_2": ["мемлекеттердің астаналары", "астаналар", "елордалар", "астана"], "score_1": ["қалалар", "елді мекендер", "қала"]},
    {"pair": ("Феодализм", "капитализм"), "score_2": ["қоғамдық-экономикалық формациялар", "формациялар", "қоғамдық формациялар"], "score_1": ["қоғам", "дәуірлер", "даму сатылары", "дәуір"]},
    {"pair": ("Батылдық", "мейірімділік"), "score_2": ["мінездің оң қасиеттері", "жақсы қасиеттер", "адам қасиеттері", "жақсы қасиет", "оң қасиеттер"], "score_1": ["қасиеттер", "тұлғаның қасиеттері", "мінез", "қасиет"]},
    {"pair": ("Су қоймасы", "канал"), "score_2": ["жасанды су құрылыстары", "су құрылыстары", "жасанды су айдындары"], "score_1": ["құрылыс", "су айдыны", "су айдындары"]},
    {"pair": ("Қосынды", "көбейтінді"), "score_2": ["математикалық амалдардың нәтижелері", "амалдардың нәтижелері", "амалдар нәтижесі"], "score_1": ["математикалық амалдар", "амалдар"]},
    {"pair": ("Ғылым", "өнер"), "score_2": ["адам қызметінің түрлері", "адам қызметі", "рухани мәдениет", "қоғамдық сана формалары"], "score_1": ["шығармашылық", "таным", "қызмет түрлері"]},
    {"pair": ("Ақуыз", "май"), "score_2": ["органикалық заттар", "органикалық зат"], "score_1": ["заттың құрамы", "нутриенттер", "қоректік заттар", "заттар"]},
    {"pair": ("Газ", "сұйықтық"), "score_2": ["заттың агрегаттық күйлері", "агрегаттық күйлер", "агрегаттық күй"], "score_1": ["зат", "дененің күйі", "күйлер"]},
    {"pair": ("Жер сілкінісі", "құйын"), "score_2": ["дүлей апаттар", "табиғи апаттар", "табиғи апат", "апаттар"], "score_1": ["табиғат құбылыстары", "құбылыстар", "табиғи құбылыстар"]},
    {"pair": ("Метафора", "аллегория"), "score_2": ["көркемдік тәсілдер", "көркемдегіш құралдар", "әдеби тәсілдер", "көркем тәсілдер", "бейнелеу құралдары"], "score_1": ["баяндау тәсілдері", "тәсілдер", "құралдар"]},
    {"pair": ("Классицизм", "романтизм"), "score_2": ["өнердегі бағыттар", "әдеби бағыттар", "ағымдар", "бағыттар"], "score_1": ["дәуірлер", "кезеңдер"]},
]
assert len(_KK_GENERALIZATION) == len(GENERALIZATION_ITEMS)

for _ru, _kk in zip(GENERALIZATION_ITEMS, _KK_GENERALIZATION, strict=True):
    _ru["pair"] = {"ru": list(_ru["pair"]), "kk": list(_kk["pair"])}
    _ru["score_2"] = {"ru": _ru["score_2"], "kk": _kk["score_2"]}
    _ru["score_1"] = {"ru": _ru["score_1"], "kk": _kk["score_1"]}


_KK_LOGICAL_SCHEMAS: list[list[str]] = [
    ["тірі жәндік", "жануар", "сүтқоректі", "мысық", "сиам мысығы"],
    ["мемлекет", "облыс", "қала", "көше", "үй"],
    ["өнер", "әдебиет", "поэзия", "сонет"],
    ["сан", "натурал сан", "жұп сан", "24"],
    ["көлік", "жер үсті көлігі", "рельсті көлік", "трамвай"],
    ["зат", "органикалық зат", "ақуыз", "фермент"],
    ["оқу орны", "мектеп", "жоғары сынып", "11-сынып"],
    ["ғылым", "жаратылыстану ғылымы", "биология", "генетика"],
]
assert len(_KK_LOGICAL_SCHEMAS) == len(LOGICAL_SCHEMA_ITEMS)

for _ru, _kk_concepts in zip(LOGICAL_SCHEMA_ITEMS, _KK_LOGICAL_SCHEMAS, strict=True):
    assert len(_ru["concepts"]) == len(_kk_concepts)
    _ru["concepts"] = {"ru": _ru["concepts"], "kk": _kk_concepts}


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

# Below: `text`/`options`/`answer`/`words`/`score_2`/`score_1`/`concepts`
# are `{ru,kk}` dicts (PRO-338 Ф4.4 fold-in above) for every subtest except
# numeric_series/geometric_figures (locale-independent content) — every
# check below runs once per locale so a translation gap can't silently ship.
for _loc in ("ru", "kk"):
    for _item in AWARENESS_ITEMS:
        _opts = _item["options"][_loc]
        assert 4 <= len(_opts) <= 5
        assert _item["answer"][_loc] in _opts
        assert _item["subject"] in SUBJECTS

    for _item in ANALOGIES_ITEMS:
        _opts = _item["options"][_loc]
        assert 4 <= len(_opts) <= 5
        assert _item["answer"][_loc] in _opts

    for _item in CLASSIFICATION_ITEMS:
        _words = _item["words"][_loc]
        _answer = _item["answer"][_loc]
        assert len(_words) == 6
        assert len(_answer) == 2
        assert set(_answer).issubset(set(_words))

    for _item in GENERALIZATION_ITEMS:
        _score_2 = _item["score_2"][_loc]
        _score_1 = _item["score_1"][_loc]
        assert _score_2 and _score_1
        assert _item["subject"] in SUBJECTS
        # A phrase must not appear in both tiers — ambiguous scoring otherwise.
        assert not set(_score_2) & set(_score_1)

    for _item in LOGICAL_SCHEMA_ITEMS:
        assert len(_item["concepts"][_loc]) >= 3

for _item in LABILITY_ITEMS:
    assert ("answer" in _item) != ("dynamic" in _item), (
        "each lability item is either fully static (answer) or dynamic "
        "(needs submission-time context) — never both, never neither"
    )
    for _loc in ("ru", "kk"):
        assert len(_item["options"][_loc]) == 2, "every lability item is a 2-way choice, rendered as buttons"
        if "answer" in _item:
            assert _item["answer"][_loc] in _item["options"][_loc]

for _item in NUMERIC_SERIES_ITEMS:
    assert len(_item["answer"]) == 2

_FIGURE_LETTERS = {"А", "Б", "В", "Г"}
for _item in GEOMETRIC_FIGURES_ITEMS:
    assert _item["answer"] in _FIGURE_LETTERS

assert set(SUBTEST_BY_NUMBER.keys()) == {1, 2, 3, 4, 5, 6, 7, 8}
assert set(SUBTEST_ITEMS.keys()) == {s["key"] for s in SUBTESTS}
for _n, _meta in SUBTEST_BY_NUMBER.items():
    assert len(SUBTEST_ITEMS[_meta["key"]]) == _meta["item_count"]
