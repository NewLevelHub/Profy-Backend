"""
RIASEC question bank — pure content, no logic.

Source: "Вопросы R.md" (148 lines from HollandCodeTestQuestionSeedData.java,
R/I/A/S/E/C-tagged). Two exact same-category duplicate lines were dropped
(original #69 "Do you like to attend concerts..." — literal repeat of #68;
original #89 "Can you teach/train others?" — literal repeat of #87), leaving
146 unique statements. Cross-category repeats of the same trait word (e.g.
"ambitious" appears under R, E and C) were kept and rephrased per-context —
those are different inventory items, not duplicates, per the source itself.

Every item is rephrased into a single "Мне нравится..." (liking-scale)
statement regardless of whether the English source was a trait ("Are you..."),
an ability ("Can you...") or an activity ("Do you like to...") question, so
the whole bank answers on one fixed 1-5 scale (see app scale in the API
schema / frontend LIKERT_SCALE constant) — see TICKET-riasec-migration.md §5.2
for the translation pattern.

Junior-tier items (see age_tier assignment below) additionally carry
`short_text`/`icon` — a short child-friendly button label + emoji, used by
the junior forced-choice-pair format instead of the full Likert statement
(TZ_Profi.md §13 bans Likert for junior). Not just a truncation: several
junior items were originally abstract trait language ("Мне свойственно
действовать осторожно и взвешенно") that a 6-9 year old can't self-report
against — short_text reframes those as concrete preferences/activities
while keeping the same RIASEC-type signal.

To change the question bank: edit this list and rerun
scripts/seed_riasec_questions.py — nothing elsewhere hardcodes question
count, text, or per-type counts.
"""

QUESTIONS: list[dict] = [
    # R — Realistic (24)
    {"riasec_type": "R", "text": "Мне нравится решать практические, приземлённые задачи", "short_text": "Чинить и мастерить", "icon": "🔧"},
    {"riasec_type": "R", "text": "Мне нравится говорить прямо и честно, без обиняков", "short_text": "Говорить прямо, как есть", "icon": "🗣️"},
    {"riasec_type": "R", "text": "Мне нравится разбираться, как устроена техника и механизмы", "short_text": "Разбирать технику", "icon": "⚙️"},
    {"riasec_type": "R", "text": "Мне нравится, когда жизнь идёт стабильно и предсказуемо", "short_text": "Когда всё по плану", "icon": "📅"},
    {"riasec_type": "R", "text": "Мне ближе конкретные вещи, чем отвлечённые рассуждения", "short_text": "Делать, а не болтать", "icon": "🔨"},
    {"riasec_type": "R", "text": "Мне комфортнее держаться сдержанно, не на виду", "short_text": "Быть в сторонке", "icon": "🤫"},
    {"riasec_type": "R", "text": "Мне нравится держать себя в руках и контролировать эмоции"},
    {"riasec_type": "R", "text": "Мне нравится действовать самостоятельно, ни от кого не завися"},
    {"riasec_type": "R", "text": "Мне нравится ставить перед собой амбициозные цели"},
    {"riasec_type": "R", "text": "Мне нравится, когда всё делается по чёткой системе"},
    {"riasec_type": "R", "text": "Мне нравится чинить сломанные электроприборы дома"},
    {"riasec_type": "R", "text": "Мне нравится искать причину поломки в технике"},
    {"riasec_type": "R", "text": "Мне нравится ставить палатку в походе"},
    {"riasec_type": "R", "text": "Мне нравится заниматься спортом"},
    {"riasec_type": "R", "text": "Мне нравится читать чертежи и схемы"},
    {"riasec_type": "R", "text": "Мне нравится сажать и выращивать растения"},
    {"riasec_type": "R", "text": "Мне нравится работать со станками и техническим оборудованием"},
    {"riasec_type": "R", "text": "Мне нравится копаться в моторах и механизмах — разбирать и собирать"},
    {"riasec_type": "R", "text": "Мне нравится работать на улице, на свежем воздухе"},
    {"riasec_type": "R", "text": "Мне нравится быть физически активным"},
    {"riasec_type": "R", "text": "Мне нравится делать что-то своими руками"},
    {"riasec_type": "R", "text": "Мне нравится строить и мастерить вещи"},
    {"riasec_type": "R", "text": "Мне нравится ухаживать за животными и дрессировать их"},
    {"riasec_type": "R", "text": "Мне нравится собирать и настраивать электронные устройства"},

    # I — Investigative (23)
    {"riasec_type": "I", "text": "Мне нравится докапываться до сути вещей", "short_text": "Узнавать, как всё устроено", "icon": "🔍"},
    {"riasec_type": "I", "text": "Мне нравится анализировать и разбираться в деталях", "short_text": "Разбираться в деталях", "icon": "🧩"},
    {"riasec_type": "I", "text": "Мне интересен научный взгляд на вещи", "short_text": "Проводить опыты", "icon": "🧪"},
    {"riasec_type": "I", "text": "Мне нравится подмечать детали и быть точным", "short_text": "Замечать мелочи", "icon": "🔎"},
    {"riasec_type": "I", "text": "Мне нравится глубоко изучать сложные темы", "short_text": "Изучать сложные темы", "icon": "📚"},
    {"riasec_type": "I", "text": "Мне свойственно действовать осторожно и взвешенно", "short_text": "Сначала подумать, потом делать", "icon": "🤔"},
    {"riasec_type": "I", "text": "Мне нравится чувствовать уверенность в своих интеллектуальных силах"},
    {"riasec_type": "I", "text": "Мне нравится разбираться в задачах самостоятельно, без подсказок"},
    {"riasec_type": "I", "text": "Мне нравится мыслить логично и последовательно"},
    {"riasec_type": "I", "text": "Мне интересны сложные, многогранные вопросы"},
    {"riasec_type": "I", "text": "Мне нравится узнавать новое из любопытства"},
    {"riasec_type": "I", "text": "Мне нравится размышлять абстрактно"},
    {"riasec_type": "I", "text": "Мне нравится решать математические задачи"},
    {"riasec_type": "I", "text": "Мне интересно разбираться в научных теориях"},
    {"riasec_type": "I", "text": "Мне нравится делать сложные расчёты"},
    {"riasec_type": "I", "text": "Мне нравится использовать микроскоп или компьютер для исследований"},
    {"riasec_type": "I", "text": "Мне нравится разбираться в формулах"},
    {"riasec_type": "I", "text": "Мне нравится исследовать разные идеи"},
    {"riasec_type": "I", "text": "Мне нравится работать независимо, без указаний"},
    {"riasec_type": "I", "text": "Мне нравится проводить лабораторные эксперименты"},
    {"riasec_type": "I", "text": "Мне нравится иметь дело с абстрактными понятиями"},
    {"riasec_type": "I", "text": "Мне нравится заниматься исследованиями"},
    {"riasec_type": "I", "text": "Мне нравится браться за сложные, непростые задачи"},

    # A — Artistic (26; source #69 exact duplicate of #68 dropped)
    {"riasec_type": "A", "text": "Мне нравится придумывать что-то новое и творческое", "short_text": "Придумывать новое", "icon": "🎨"},
    {"riasec_type": "A", "text": "Мне нравится фантазировать и придумывать целые истории в голове", "short_text": "Сочинять истории", "icon": "📖"},
    {"riasec_type": "A", "text": "Мне нравится предлагать нестандартные, инновационные решения", "short_text": "Находить необычные решения", "icon": "💡"},
    {"riasec_type": "A", "text": "Мне комфортно отступать от привычных правил", "short_text": "Делать не как все", "icon": "🌀"},
    {"riasec_type": "A", "text": "Мне нравится ярко и эмоционально переживать происходящее вокруг", "short_text": "Ярко всё чувствовать", "icon": "🌟"},
    {"riasec_type": "A", "text": "Мне нравится иметь свободу для творческого самовыражения", "short_text": "Творить, как хочется", "icon": "🖌️"},
    {"riasec_type": "A", "text": "Мне нравится ярко выражать себя", "short_text": "Быть ярким и заметным", "icon": "✨"},
    {"riasec_type": "A", "text": "Мне нравится делать всё по-своему, оригинально"},
    {"riasec_type": "A", "text": "Мне нравится размышлять о своих чувствах и мыслях"},
    {"riasec_type": "A", "text": "Иногда мне нравится действовать по первому порыву"},
    {"riasec_type": "A", "text": "Мне нравится подмечать тонкие детали настроения и атмосферы"},
    {"riasec_type": "A", "text": "Мне не страшно пробовать смелые, необычные идеи"},
    {"riasec_type": "A", "text": "Мне интересны сложные, неоднозначные вещи"},
    {"riasec_type": "A", "text": "Мне нравится оставаться верным своим идеалам"},
    {"riasec_type": "A", "text": "Мне не обязательно подстраиваться под общепринятое"},
    {"riasec_type": "A", "text": "Мне нравится рисовать и делать наброски"},
    {"riasec_type": "A", "text": "Мне нравится играть на музыкальном инструменте"},
    {"riasec_type": "A", "text": "Мне нравится сочинять истории, стихи или музыку"},
    {"riasec_type": "A", "text": "Мне нравится петь, играть в спектаклях или танцевать"},
    {"riasec_type": "A", "text": "Мне нравится придумывать образы в одежде или интерьере"},
    {"riasec_type": "A", "text": "Мне нравится ходить на концерты, в театр, на выставки"},
    {"riasec_type": "A", "text": "Мне нравится читать художественную литературу, пьесы и стихи"},
    {"riasec_type": "A", "text": "Мне нравится заниматься рукоделием и творческими поделками"},
    {"riasec_type": "A", "text": "Мне нравится фотографировать"},
    {"riasec_type": "A", "text": "Мне нравится выражать себя через творчество"},
    {"riasec_type": "A", "text": "Мне интересно иметь дело с неоднозначными, открытыми идеями"},

    # S — Social (23; source #89 exact duplicate of #87 dropped)
    {"riasec_type": "S", "text": "Мне нравится дружелюбно относиться к людям", "short_text": "Дружить со всеми", "icon": "🤝"},
    {"riasec_type": "S", "text": "Мне нравится быть полезным другим", "short_text": "Помогать другим", "icon": "🤗"},
    {"riasec_type": "S", "text": "Мне нравится следовать своим убеждениям, помогая другим", "short_text": "Заступаться за других", "icon": "🛡️"},
    {"riasec_type": "S", "text": "Мне нравится подмечать, что на самом деле чувствует человек", "short_text": "Понимать чувства других", "icon": "💗"},
    {"riasec_type": "S", "text": "Мне легко общаться с новыми людьми", "short_text": "Знакомиться с новыми людьми", "icon": "👋"},
    {"riasec_type": "S", "text": "Мне нравится вставать на место другого человека и понимать его", "short_text": "Представлять себя на месте другого", "icon": "🎭"},
    {"riasec_type": "S", "text": "Мне нравится сотрудничать с другими"},
    {"riasec_type": "S", "text": "Мне нравится делиться и помогать, не задумываясь"},
    {"riasec_type": "S", "text": "Мне нравится быть тем, на кого можно положиться"},
    {"riasec_type": "S", "text": "Мне легко прощать и не держать обиды"},
    {"riasec_type": "S", "text": "Мне нравится сохранять терпение, даже если с человеком непросто"},
    {"riasec_type": "S", "text": "Мне нравится проявлять доброту к окружающим"},
    {"riasec_type": "S", "text": "Мне нравится учить и объяснять что-то другим"},
    {"riasec_type": "S", "text": "Мне нравится ясно и понятно выражать свои мысли"},
    {"riasec_type": "S", "text": "Мне нравится вести групповое обсуждение"},
    {"riasec_type": "S", "text": "Мне нравится улаживать споры между людьми"},
    {"riasec_type": "S", "text": "Мне нравится планировать и руководить каким-то делом"},
    {"riasec_type": "S", "text": "Мне нравится хорошо взаимодействовать с другими в команде"},
    {"riasec_type": "S", "text": "Мне нравится работать в группе"},
    {"riasec_type": "S", "text": "Мне нравится помогать людям решать их проблемы"},
    {"riasec_type": "S", "text": "Мне нравится заниматься волонтёрством"},
    {"riasec_type": "S", "text": "Мне нравится работать с детьми и подростками"},
    {"riasec_type": "S", "text": "Мне нравится быть полезным и служить другим"},

    # E — Enterprising (24)
    {"riasec_type": "E", "text": "Мне нравится чувствовать уверенность в себе", "short_text": "Быть уверенным в себе", "icon": "💪"},
    {"riasec_type": "E", "text": "Мне нравится уверенно отстаивать своё мнение", "short_text": "Отстаивать своё мнение", "icon": "📢"},
    {"riasec_type": "E", "text": "Мне легко убеждать людей в своей правоте", "short_text": "Убеждать других", "icon": "🗯️"},
    {"riasec_type": "E", "text": "Мне нравится быть активным и полным энергии", "short_text": "Быть заводилой", "icon": "⚡"},
    {"riasec_type": "E", "text": "Мне нравится рисковать и пробовать новое", "short_text": "Пробовать рискованное", "icon": "🎢"},
    {"riasec_type": "E", "text": "Мне нравится добиваться высоких результатов", "short_text": "Быть первым", "icon": "🏆"},
    {"riasec_type": "E", "text": "Мне легко находить общий язык с людьми"},
    {"riasec_type": "E", "text": "Мне нравится много говорить и общаться"},
    {"riasec_type": "E", "text": "Мне комфортно быть в центре внимания среди людей"},
    {"riasec_type": "E", "text": "Мне нравится действовать спонтанно, без долгого планирования"},
    {"riasec_type": "E", "text": "Мне нравится смотреть на вещи с оптимизмом"},
    {"riasec_type": "E", "text": "Мне нравится запускать новые проекты"},
    {"riasec_type": "E", "text": "Мне нравится убеждать людей делать по-моему"},
    {"riasec_type": "E", "text": "Мне нравится продавать вещи и идеи"},
    {"riasec_type": "E", "text": "Мне нравится выступать перед людьми"},
    {"riasec_type": "E", "text": "Мне нравится организовывать мероприятия"},
    {"riasec_type": "E", "text": "Мне нравится вести за собой группу людей"},
    {"riasec_type": "E", "text": "Мне нравится уговаривать и убеждать других"},
    {"riasec_type": "E", "text": "Мне нравится принимать решения"},
    {"riasec_type": "E", "text": "Мне хотелось бы, чтобы меня выбрали на руководящую должность"},
    {"riasec_type": "E", "text": "Мне нравится идея начать своё дело"},
    {"riasec_type": "E", "text": "Мне было бы интересно участвовать в политической кампании"},
    {"riasec_type": "E", "text": "Мне нравится знакомиться с влиятельными людьми"},
    {"riasec_type": "E", "text": "Мне нравится иметь влияние и высокий статус"},

    # C — Conventional (26)
    {"riasec_type": "C", "text": "Мне нравится, когда всё хорошо организовано", "short_text": "Когда всё разложено по местам", "icon": "🗂️"},
    {"riasec_type": "C", "text": "Мне нравится быть точным в деталях", "short_text": "Быть аккуратным", "icon": "✅"},
    {"riasec_type": "C", "text": "Мне нравится, когда нужно быстро что-то посчитать в уме", "short_text": "Считать в уме", "icon": "🔢"},
    {"riasec_type": "C", "text": "Мне нравится действовать по чёткому методу", "short_text": "Делать по инструкции", "icon": "📋"},
    {"riasec_type": "C", "text": "Мне нравится добросовестно выполнять свои обязанности", "short_text": "Доводить дело до конца", "icon": "✔️"},
    {"riasec_type": "C", "text": "Мне нравится делать всё эффективно, без лишних затрат", "short_text": "Не тратить время зря", "icon": "⏱️"},
    {"riasec_type": "C", "text": "Мне комфортно следовать установленным правилам", "short_text": "Играть по правилам", "icon": "📏"},
    {"riasec_type": "C", "text": "Мне нравится подходить к делу практично"},
    {"riasec_type": "C", "text": "Мне нравится экономно и бережливо относиться к деньгам"},
    {"riasec_type": "C", "text": "Мне нравится, когда всё разложено по системе"},
    {"riasec_type": "C", "text": "Мне нравится, когда всё чётко структурировано"},
    {"riasec_type": "C", "text": "Мне нравится быть вежливым и корректным"},
    {"riasec_type": "C", "text": "Мне нравится доводить дело до высокого результата"},
    {"riasec_type": "C", "text": "Мне комфортно следовать указаниям"},
    {"riasec_type": "C", "text": "Мне нравится доводить начатое до конца, даже если сложно"},
    {"riasec_type": "C", "text": "Мне нравится работать в рамках чёткой системы правил"},
    {"riasec_type": "C", "text": "Мне нравится быстро и много работать с документами"},
    {"riasec_type": "C", "text": "Мне нравится вести точные записи и отчётность"},
    {"riasec_type": "C", "text": "Мне нравится работать с компьютером и базами данных"},
    {"riasec_type": "C", "text": "Мне нравится грамотно составлять деловые письма"},
    {"riasec_type": "C", "text": "Мне нравится следовать чётко прописанным процедурам"},
    {"riasec_type": "C", "text": "Мне нравится работать с программами обработки данных"},
    {"riasec_type": "C", "text": "Мне нравится решать задачи, где много цифр и расчётов"},
    {"riasec_type": "C", "text": "Мне нравится печатать и быстро вести запись информации"},
    {"riasec_type": "C", "text": "Мне нравится нести ответственность за мелкие детали"},
    {"riasec_type": "C", "text": "Мне нравится коллекционировать и упорядочивать вещи"},
]

# order is assigned by position — editing this list (add/remove/reorder) and
# rerunning the seed script is the entire "change the question bank" workflow.
for _i, _q in enumerate(QUESTIONS, start=1):
    _q["order"] = _i

# age_tier: junior/middle get a PREFIX of each type's items (not a separate
# curated set) — first ceil(n/4) items of a type are junior-visible, first
# ceil(n/2) are middle-visible, all are senior-visible. Computed from the
# bank's own per-type counts, never hardcoded, so editing the bank keeps the
# 1/2/4 ratio automatically.
import math  # noqa: E402
from collections import Counter  # noqa: E402

_type_totals = Counter(_q["riasec_type"] for _q in QUESTIONS)
_type_seen: dict[str, int] = dict.fromkeys(_type_totals, 0)

for _q in QUESTIONS:
    _type = _q["riasec_type"]
    _n = _type_totals[_type]
    _junior_cut = math.ceil(_n / 4)
    _middle_cut = math.ceil(_n / 2)
    _pos = _type_seen[_type]
    _type_seen[_type] += 1
    if _pos < _junior_cut:
        _q["age_tier"] = "junior"
    elif _pos < _middle_cut:
        _q["age_tier"] = "middle"
    else:
        _q["age_tier"] = "senior"
    if _q["age_tier"] != "junior":
        assert "short_text" not in _q, f"non-junior item unexpectedly has short_text: {_q['text']!r}"

assert len(QUESTIONS) == 146, f"expected 146 unique questions, got {len(QUESTIONS)}"
assert sum(1 for _q in QUESTIONS if _q.get("short_text")) == 38, "expected exactly 38 junior short_text items"
