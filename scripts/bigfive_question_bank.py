"""
Big Five question bank — pure content, no logic.

Source: Johnson's IPIP-NEO-120 (public domain), Russian translation from the
`b5-johnson-120-ipip-neo-pi-r` npm package (data/ru/questions.json), with 9
items rewritten in `BigFive тестирование.md` to remove political framing and
content too heavy for under-18 respondents (same domain/facet/keyed slot
preserved for each rewrite, so the scoring key is unaffected).

120 items, 5 domains (N/E/O/A/C) x 6 facets x 4 items. `keyed` marks the
direction of the item: `minus` items are reverse-scored at read time
(app/services/bigfive_service.py), never inverted here or at storage time.

Block-1 items (age_tier="junior", assigned below) additionally carry
`short_text`/`icon` — a short child-friendly button label + emoji, used by
the junior forced-choice-pair format instead of the full Likert statement
(TZ_Profi.md §13 bans Likert for junior).

To change the question bank: edit this list and rerun
scripts/seed_bigfive_questions.py — nothing elsewhere hardcodes question
count, text, or per-domain/per-facet counts.
"""

QUESTIONS: list[dict] = [
    {"bigfive_domain": "N", "facet": 1, "keyed": "plus", "text": "Переживаю о разном", "short_text": "Часто переживаю", "icon": "😟"},
    {"bigfive_domain": "E", "facet": 1, "keyed": "plus", "text": "С легкостью завожу друзей", "short_text": "Легко завожу друзей", "icon": "👋"},
    {"bigfive_domain": "O", "facet": 1, "keyed": "plus", "text": "Имею яркое воображение", "short_text": "У меня богатая фантазия", "icon": "🌈"},
    {"bigfive_domain": "A", "facet": 1, "keyed": "plus", "text": "Доверяю другим", "short_text": "Доверяю людям", "icon": "🤝"},
    {"bigfive_domain": "C", "facet": 1, "keyed": "plus", "text": "Завершаю задачи успешно", "short_text": "Довожу дела до конца", "icon": "✅"},
    {"bigfive_domain": "N", "facet": 2, "keyed": "plus", "text": "Легко начинаю злиться", "short_text": "Быстро злюсь", "icon": "😠"},
    {"bigfive_domain": "E", "facet": 2, "keyed": "plus", "text": "Люблю большие вечеринки", "short_text": "Люблю шумные праздники", "icon": "🎉"},
    {"bigfive_domain": "O", "facet": 2, "keyed": "plus", "text": "Верю в важность искусства", "short_text": "Люблю искусство", "icon": "🎨"},
    {"bigfive_domain": "A", "facet": 2, "keyed": "minus", "text": "Использую других ради личных целей", "short_text": "Использую других для своей выгоды", "icon": "😏"},
    {"bigfive_domain": "C", "facet": 2, "keyed": "plus", "text": "Люблю прибраться", "short_text": "Люблю наводить порядок", "icon": "🧹"},
    {"bigfive_domain": "N", "facet": 3, "keyed": "plus", "text": "Часто грущу", "short_text": "Часто грущу", "icon": "😢"},
    {"bigfive_domain": "E", "facet": 3, "keyed": "plus", "text": "Беру на себя ответственность", "short_text": "Беру на себя главное", "icon": "🙋"},
    {"bigfive_domain": "O", "facet": 3, "keyed": "plus", "text": "Остро переживаю свои эмоции", "short_text": "Сильно всё чувствую", "icon": "💗"},
    {"bigfive_domain": "A", "facet": 3, "keyed": "plus", "text": "Люблю помогать другим", "short_text": "Люблю помогать", "icon": "🤗"},
    {"bigfive_domain": "C", "facet": 3, "keyed": "plus", "text": "Сдерживаю обещания", "short_text": "Держу слово", "icon": "🤞"},
    {"bigfive_domain": "N", "facet": 4, "keyed": "plus", "text": "Нахожу трудным обращаться к людям", "short_text": "Стесняюсь обращаться к людям", "icon": "😳"},
    {"bigfive_domain": "E", "facet": 4, "keyed": "plus", "text": "У меня всегда много дел", "short_text": "У меня всегда много дел", "icon": "🏃"},
    {"bigfive_domain": "O", "facet": 4, "keyed": "plus", "text": "Предпочитаю разнообразие рутине", "short_text": "Люблю разнообразие", "icon": "🔀"},
    {"bigfive_domain": "A", "facet": 4, "keyed": "minus", "text": "Люблю хорошую потасовку", "short_text": "Люблю подраться в шутку", "icon": "🤼"},
    {"bigfive_domain": "C", "facet": 4, "keyed": "plus", "text": "Много работаю", "short_text": "Много стараюсь", "icon": "💼"},
    {"bigfive_domain": "N", "facet": 5, "keyed": "plus", "text": "Иногда не могу вовремя остановиться", "short_text": "Иногда не могу остановиться", "icon": "🛑"},
    {"bigfive_domain": "E", "facet": 5, "keyed": "plus", "text": "Люблю эмоциональное волнение", "short_text": "Люблю адреналин", "icon": "🎢"},
    {"bigfive_domain": "O", "facet": 5, "keyed": "plus", "text": "Люблю читать что-то посложнее", "short_text": "Люблю сложные книги", "icon": "📖"},
    {"bigfive_domain": "A", "facet": 5, "keyed": "minus", "text": "Считаю, что я лучше других", "short_text": "Считаю себя лучше других", "icon": "😤"},
    {"bigfive_domain": "C", "facet": 5, "keyed": "plus", "text": "У меня есть план на случай неожиданностей", "short_text": "У меня есть план на всякий случай", "icon": "🗺️"},
    {"bigfive_domain": "N", "facet": 6, "keyed": "plus", "text": "Легко паникую", "short_text": "Легко паникую", "icon": "😱"},
    {"bigfive_domain": "E", "facet": 6, "keyed": "plus", "text": "Излучаю позитив", "short_text": "Всегда в хорошем настроении", "icon": "☀️"},
    {"bigfive_domain": "O", "facet": 6, "keyed": "plus", "text": "Мне интересно узнавать о разных культурах и непривычных для меня традициях", "short_text": "Люблю узнавать о других странах", "icon": "🌍"},
    {"bigfive_domain": "A", "facet": 6, "keyed": "plus", "text": "Сопереживаю бездомным", "short_text": "Жалею тех, кому трудно", "icon": "💔"},
    {"bigfive_domain": "C", "facet": 6, "keyed": "minus", "text": "Начинаю разные вещи не подумав", "short_text": "Берусь за всё не подумав", "icon": "🌪️"},

    {"bigfive_domain": "N", "facet": 1, "keyed": "plus", "text": "Опасаюсь худшего"},
    {"bigfive_domain": "E", "facet": 1, "keyed": "plus", "text": "Чувствую себя комфортно в окружении людей"},
    {"bigfive_domain": "O", "facet": 1, "keyed": "plus", "text": "Могу представить то, чего никогда не было"},
    {"bigfive_domain": "A", "facet": 1, "keyed": "plus", "text": "Верю в хорошие намерения людей"},
    {"bigfive_domain": "C", "facet": 1, "keyed": "plus", "text": "Мне отлично удаётся то, чем я занимаюсь"},
    {"bigfive_domain": "N", "facet": 2, "keyed": "plus", "text": "Легко раздражаюсь"},
    {"bigfive_domain": "E", "facet": 2, "keyed": "plus", "text": "Разговариваю с разными людьми на вечеринках"},
    {"bigfive_domain": "O", "facet": 2, "keyed": "plus", "text": "Вижу красоту там, где другие не видят"},
    {"bigfive_domain": "A", "facet": 2, "keyed": "minus", "text": "Иногда думаю в первую очередь о своей выгоде, а не о других"},
    {"bigfive_domain": "C", "facet": 2, "keyed": "minus", "text": "Часто забываю класть вещи на место"},
    {"bigfive_domain": "N", "facet": 3, "keyed": "plus", "text": "Часто чувствую недовольство собой"},
    {"bigfive_domain": "E", "facet": 3, "keyed": "plus", "text": "Стараюсь быть лидером"},
    {"bigfive_domain": "O", "facet": 3, "keyed": "plus", "text": "Сопереживаю другим людям"},
    {"bigfive_domain": "A", "facet": 3, "keyed": "plus", "text": "Беспокоюсь за других людей"},
    {"bigfive_domain": "C", "facet": 3, "keyed": "plus", "text": "Говорю правду"},
    {"bigfive_domain": "N", "facet": 4, "keyed": "plus", "text": "Боюсь привлекать внимание к себе"},
    {"bigfive_domain": "E", "facet": 4, "keyed": "plus", "text": "Всегда куда-то бегу"},
    {"bigfive_domain": "O", "facet": 4, "keyed": "minus", "text": "Предпочитаю заниматься тем, что уже знаю"},
    {"bigfive_domain": "A", "facet": 4, "keyed": "minus", "text": "Кричу на людей"},
    {"bigfive_domain": "C", "facet": 4, "keyed": "plus", "text": "Делаю больше, чем от меня ожидают"},
    {"bigfive_domain": "N", "facet": 5, "keyed": "minus", "text": "Редко злоупотребляю чем-либо"},
    {"bigfive_domain": "E", "facet": 5, "keyed": "plus", "text": "Ищу приключений"},
    {"bigfive_domain": "O", "facet": 5, "keyed": "minus", "text": "Избегаю философских рассуждений"},
    {"bigfive_domain": "A", "facet": 5, "keyed": "minus", "text": "Очень высоко ставлю себя"},
    {"bigfive_domain": "C", "facet": 5, "keyed": "plus", "text": "Придерживаюсь своих планов"},
    {"bigfive_domain": "N", "facet": 6, "keyed": "plus", "text": "События легко выбивают меня из колеи"},
    {"bigfive_domain": "E", "facet": 6, "keyed": "plus", "text": "Много веселюсь"},
    {"bigfive_domain": "O", "facet": 6, "keyed": "plus", "text": "Верю, что нет абсолютного правильного и неправильного"},
    {"bigfive_domain": "A", "facet": 6, "keyed": "plus", "text": "Сопереживаю тем, кому хуже, чем мне"},
    {"bigfive_domain": "C", "facet": 6, "keyed": "minus", "text": "Принимаю поспешные решения"},

    {"bigfive_domain": "N", "facet": 1, "keyed": "plus", "text": "Многого боюсь"},
    {"bigfive_domain": "E", "facet": 1, "keyed": "minus", "text": "Избегаю контактов с другими"},
    {"bigfive_domain": "O", "facet": 1, "keyed": "plus", "text": "Часто представляю разные варианты того, как всё может сложиться"},
    {"bigfive_domain": "A", "facet": 1, "keyed": "plus", "text": "Мне легко положиться на других людей"},
    {"bigfive_domain": "C", "facet": 1, "keyed": "plus", "text": "Легко справляюсь с задачами"},
    {"bigfive_domain": "N", "facet": 2, "keyed": "plus", "text": "Легко теряю самообладание"},
    {"bigfive_domain": "E", "facet": 2, "keyed": "minus", "text": "Предпочитаю побыть в одиночестве"},
    {"bigfive_domain": "O", "facet": 2, "keyed": "minus", "text": "Не люблю поэзию"},
    {"bigfive_domain": "A", "facet": 2, "keyed": "minus", "text": "Использую других людей при возможности"},
    {"bigfive_domain": "C", "facet": 2, "keyed": "minus", "text": "Оставляю комнату в беспорядке"},
    {"bigfive_domain": "N", "facet": 3, "keyed": "plus", "text": "Иногда мне бывает грустно без особой причины"},
    {"bigfive_domain": "E", "facet": 3, "keyed": "plus", "text": "Стараюсь взять ситуацию под контроль, когда это нужно"},
    {"bigfive_domain": "O", "facet": 3, "keyed": "minus", "text": "Редко замечаю свои эмоциональные реакции"},
    {"bigfive_domain": "A", "facet": 3, "keyed": "minus", "text": "Мне безразличны чувства других"},
    {"bigfive_domain": "C", "facet": 3, "keyed": "minus", "text": "Нарушаю правила"},
    {"bigfive_domain": "N", "facet": 4, "keyed": "plus", "text": "Чувствую себя комфортно только с друзьями"},
    {"bigfive_domain": "E", "facet": 4, "keyed": "plus", "text": "В свободное время занимаюсь много чем"},
    {"bigfive_domain": "O", "facet": 4, "keyed": "minus", "text": "Не люблю перемены"},
    {"bigfive_domain": "A", "facet": 4, "keyed": "minus", "text": "Иногда говорю людям неприятные вещи, когда злюсь"},
    {"bigfive_domain": "C", "facet": 4, "keyed": "minus", "text": "Делаю лишь столько, сколько достаточно"},
    {"bigfive_domain": "N", "facet": 5, "keyed": "minus", "text": "Легко противостою соблазнам"},
    {"bigfive_domain": "E", "facet": 5, "keyed": "plus", "text": "Мне нравится делать безрассудные вещи"},
    {"bigfive_domain": "O", "facet": 5, "keyed": "minus", "text": "С трудом понимаю абстрактные идеи"},
    {"bigfive_domain": "A", "facet": 5, "keyed": "minus", "text": "О себе высокого мнения"},
    {"bigfive_domain": "C", "facet": 5, "keyed": "minus", "text": "Трачу время понапрасну"},
    {"bigfive_domain": "N", "facet": 6, "keyed": "plus", "text": "Иногда чувствую, что дела наваливаются больше, чем я успеваю"},
    {"bigfive_domain": "E", "facet": 6, "keyed": "plus", "text": "Люблю жизнь"},
    {"bigfive_domain": "O", "facet": 6, "keyed": "minus", "text": "Считаю, что старые правила и традиции всегда лучше новых идей"},
    {"bigfive_domain": "A", "facet": 6, "keyed": "minus", "text": "Не интересуют проблемы других людей"},
    {"bigfive_domain": "C", "facet": 6, "keyed": "minus", "text": "Говорю первое, что приходит в голову, не подумав"},

    {"bigfive_domain": "N", "facet": 1, "keyed": "plus", "text": "Легко впадаю в стресс"},
    {"bigfive_domain": "E", "facet": 1, "keyed": "minus", "text": "Держу других на дистанции"},
    {"bigfive_domain": "O", "facet": 1, "keyed": "plus", "text": "Иногда так погружаюсь в свои мысли, что забываю обо всём вокруг"},
    {"bigfive_domain": "A", "facet": 1, "keyed": "minus", "text": "Не доверяю людям"},
    {"bigfive_domain": "C", "facet": 1, "keyed": "plus", "text": "Знаю, как доводить дела до конца"},
    {"bigfive_domain": "N", "facet": 2, "keyed": "minus", "text": "Не раздражаюсь легко"},
    {"bigfive_domain": "E", "facet": 2, "keyed": "minus", "text": "Избегаю толпы"},
    {"bigfive_domain": "O", "facet": 2, "keyed": "minus", "text": "Не наслаждаюсь музеями искусства"},
    {"bigfive_domain": "A", "facet": 2, "keyed": "minus", "text": "Мешаю планам других людей"},
    {"bigfive_domain": "C", "facet": 2, "keyed": "minus", "text": "Оставляю вещи где попало"},
    {"bigfive_domain": "N", "facet": 3, "keyed": "minus", "text": "Мне спокойно наедине с собой"},
    {"bigfive_domain": "E", "facet": 3, "keyed": "minus", "text": "Жду, что другие покажут мне путь"},
    {"bigfive_domain": "O", "facet": 3, "keyed": "minus", "text": "Не понимаю эмоциональных людей"},
    {"bigfive_domain": "A", "facet": 3, "keyed": "minus", "text": "Не уделяю времени другим людям"},
    {"bigfive_domain": "C", "facet": 3, "keyed": "minus", "text": "Нарушаю мои обещания"},
    {"bigfive_domain": "N", "facet": 4, "keyed": "minus", "text": "Проблемные социальные ситуации не беспокоят меня"},
    {"bigfive_domain": "E", "facet": 4, "keyed": "minus", "text": "Предпочитаю не спешить и никуда не бежать"},
    {"bigfive_domain": "O", "facet": 4, "keyed": "minus", "text": "Придерживаюсь старых устоев"},
    {"bigfive_domain": "A", "facet": 4, "keyed": "minus", "text": "Долго не могу простить, если меня обидели"},
    {"bigfive_domain": "C", "facet": 4, "keyed": "minus", "text": "Вкладываю мало времени и стараний в то, что делаю"},
    {"bigfive_domain": "N", "facet": 5, "keyed": "minus", "text": "Умею контролировать свои желания"},
    {"bigfive_domain": "E", "facet": 5, "keyed": "plus", "text": "Веду себя дико и безумно"},
    {"bigfive_domain": "O", "facet": 5, "keyed": "minus", "text": "Меня не интересуют теоретические рассуждения"},
    {"bigfive_domain": "A", "facet": 5, "keyed": "minus", "text": "Хвастаюсь своими достоинствами"},
    {"bigfive_domain": "C", "facet": 5, "keyed": "minus", "text": "С трудом что-либо начинаю"},
    {"bigfive_domain": "N", "facet": 6, "keyed": "minus", "text": "Сохраняю самообладание в стрессовых ситуациях"},
    {"bigfive_domain": "E", "facet": 6, "keyed": "plus", "text": "Смотрю на положительную сторону жизни"},
    {"bigfive_domain": "O", "facet": 6, "keyed": "minus", "text": "Считаю, что есть только один правильный взгляд на вещи, и я его придерживаюсь"},
    {"bigfive_domain": "A", "facet": 6, "keyed": "minus", "text": "Стараюсь не думать о нуждающихся"},
    {"bigfive_domain": "C", "facet": 6, "keyed": "minus", "text": "Делаю то, что хочется прямо сейчас, не думая о последствиях"},
]

assert len(QUESTIONS) == 120

# Continues the RIASEC bank's order sequence (never hardcoded — derived from
# the actual RIASEC bank length, so the two banks never collide regardless of
# how either one's size changes).
from scripts.riasec_question_bank import QUESTIONS as _RIASEC_QUESTIONS  # noqa: E402

_BASE = len(_RIASEC_QUESTIONS)
for _i, _q in enumerate(QUESTIONS, start=_BASE + 1):
    _q["order"] = _i
    _q["instrument"] = "big_five"

# age_tier: the 120 items are laid out as 4 blocks of 30 (each block = one
# full pass through all 30 domain x facet combos). Cutting whole blocks
# — not individual items — guarantees every facet still has >=1 item at
# every age tier, which thinking_style_service.compute() depends on (it
# reads specific facets O1/O2/C1/C2/C4). Block 0 -> junior, block 1 also
# unlocks at middle, blocks 2-3 are senior-only.
for _idx, _q in enumerate(QUESTIONS):
    _block = _idx // 30
    if _block == 0:
        _q["age_tier"] = "junior"
    elif _block == 1:
        _q["age_tier"] = "middle"
    else:
        _q["age_tier"] = "senior"
    if _q["age_tier"] != "junior":
        assert "short_text" not in _q, f"non-junior item unexpectedly has short_text: {_q['text']!r}"

assert sum(1 for _q in QUESTIONS if _q.get("short_text")) == 30, "expected exactly 30 junior short_text items"
