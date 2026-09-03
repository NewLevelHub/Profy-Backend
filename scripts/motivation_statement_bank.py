"""
Motivation statement bank — pure content + combinatorics, no scoring logic.

9 categories (SDT + work-values, see TZ_Profi.md §11.2/Приложение A), measured
via forced-choice triplets (MOST/LEAST) instead of Likert — direct "how
important is X" scales flatten on value/motivation items (near-universal
"everything is important" answers), forced-choice avoids that.

Pairing is generated, not hand-picked: 9 categories = 9 points of a 3x3 grid,
12 triplets = the 12 lines of the affine plane AG(2,3) (Steiner Triple System
STS(9)) — 3 "vertical" lines + 9 "sloped" lines (3 slopes x 3 intercepts,
mod 3). Property of this construction (verified numerically, not just
asserted): every category appears in exactly 4 lines, and every PAIR of
categories co-occurs in exactly 1 line — a balanced design with no manual
pairing work and no risk of two categories facing off twice while another
pair never meets.

To change the question content: edit PHRASES (must stay 9 keys x 4 phrases).
To change the pairing: don't — the AG(2,3) generator is what stays balanced.
Rerun scripts/seed_motivation_statements.py after any edit.
"""

CATEGORIES: list[str] = [
    "interest", "challenge", "helping", "freedom", "money",
    "recognition", "stability", "creation", "teamwork",
]

# 9 categories x 4 phrasings each — one consistent infinitive-first pattern,
# so no phrase reads as "more serious" or "more casual" than another (would
# bias forced-choice toward the better-written option instead of the value).
PHRASES: dict[str, list[str]] = {
    "interest": [
        "Заниматься тем, что мне по-настоящему интересно",
        "Делать то, что увлекает меня само по себе, а не ради результата",
        "Погружаться в дело, которое меня искренне зацепило",
        "Работать над тем, что мне интересно узнавать и пробовать",
    ],
    "challenge": [
        "Решать сложные задачи, за которые не все берутся",
        "Браться за то, что сначала кажется мне не по силам",
        "Постоянно учиться новому и расти в мастерстве",
        "Проверять себя на действительно трудных задачах",
    ],
    "helping": [
        "Приносить пользу людям и помогать им",
        "Делать что-то, что реально облегчает жизнь другим",
        "Быть полезным тем, кто нуждается в помощи",
        "Работать ради того, чтобы другим стало лучше",
    ],
    "freedom": [
        "Самому решать, что и как делать, без чужого контроля",
        "Работать в своём темпе, без жёстких указаний",
        "Самому выбирать, чем и когда заниматься",
        "Иметь свободу принимать решения без разрешения сверху",
    ],
    "money": [
        "Зарабатывать много денег",
        "Получать хороший доход за свою работу",
        "Иметь возможность ни в чём себе не отказывать",
        "Зарабатывать столько, чтобы не думать о деньгах",
    ],
    "recognition": [
        "Быть тем, кого уважают и ценят за мастерство",
        "Стать известным экспертом в своём деле",
        "Получать признание за то, что я делаю хорошо",
        "Чтобы другие видели во мне профессионала",
    ],
    "stability": [
        "Иметь стабильную работу, где всё предсказуемо",
        "Знать заранее, что будет завтра и через год",
        "Работать там, где не бывает неожиданных перемен",
        "Иметь надёжное дело, в котором я уверен",
    ],
    "creation": [
        "Создать что-то своё — проект, дело, продукт",
        "Придумать и построить что-то с нуля",
        "Запустить собственное дело",
        "Оставить после себя что-то, что я создал сам",
    ],
    "teamwork": [
        "Работать в команде, где все друг друга поддерживают",
        "Делать общее дело вместе с другими людьми",
        "Быть частью сильной, дружной команды",
        "Достигать результата вместе, а не в одиночку",
    ],
}

assert set(PHRASES) == set(CATEGORIES)
assert all(len(v) == 4 for v in PHRASES.values())

# Junior (6-9) rewrite of PHRASES — same category, same position (index N of
# a category here is the junior version of PHRASES[category][N], paired 1:1
# in the STATEMENTS loop below) — worded around school/friends/hobbies
# instead of career/money/work, since a 6-9 year old has no personal
# experience of "a stable job" or "earning money". Shown instead of `text`
# only for junior profiles (app/routers/motivation.py); middle/senior are
# unaffected. Same tone-neutral principle as PHRASES: all 4 phrasings of a
# category read at the same register, so forced-choice isn't biased toward
# the better-written option.
PHRASES_JUNIOR: dict[str, list[str]] = {
    "interest": [
        "Делать то, что мне по-настоящему нравится",
        "Заниматься тем, что увлекает, даже если не за оценку",
        "С головой уходить в то, что меня зацепило",
        "Пробовать и узнавать то, что мне любопытно",
    ],
    "challenge": [
        "Решать трудные задачи, которые не все берутся решать",
        "Пробовать то, что сначала кажется слишком трудным",
        "Постоянно учиться новому и становиться лучше",
        "Проверять себя на по-настоящему трудных заданиях",
    ],
    "helping": [
        "Помогать людям и быть им полезным",
        "Делать что-то, что правда помогает другим",
        "Быть рядом с теми, кому нужна помощь",
        "Стараться, чтобы другим было лучше",
    ],
    "freedom": [
        "Самому решать, что и как делать",
        "Делать всё в своём темпе, без строгих указаний",
        "Самому решать, чем заняться прямо сейчас",
        "Делать по-своему, не спрашивая разрешения",
    ],
    "money": [
        "Получать много всего хорошего за старания",
        "Получать хорошую награду за то, что делаю",
        "Иметь возможность покупать себе, что хочется",
        "Получать достаточно, чтобы ни о чём не беспокоиться",
    ],
    "recognition": [
        "Чтобы меня уважали за то, что я умею",
        "Стать тем, кто лучше всех разбирается в своём деле",
        "Чтобы замечали, когда я делаю что-то хорошо",
        "Чтобы другие видели, что я в этом хорош",
    ],
    "stability": [
        "Чтобы моя жизнь была спокойной и предсказуемой",
        "Знать заранее, что будет завтра",
        "Заниматься тем, где не бывает внезапных перемен",
        "Заниматься тем, в чём я уверен",
    ],
    "creation": [
        "Создать что-то своё, что раньше не существовало",
        "Придумать и сделать что-то с нуля",
        "Собрать или смастерить что-то своё",
        "Оставить после себя то, что я сам придумал и сделал",
    ],
    "teamwork": [
        "Быть в команде, где все друг друга поддерживают",
        "Делать общее дело вместе с другими",
        "Быть частью дружной команды",
        "Добиваться результата вместе, а не одному",
    ],
}

assert set(PHRASES_JUNIOR) == set(CATEGORIES)
assert all(len(v) == 4 for v in PHRASES_JUNIOR.values())

# ── Kazakh (kk) — KZ-305 ──────────────────────────────────────────────────────
#
# LLM-primary translation against docs/i18n.md's glossary; native review pending
# (checklist: ProfOr/Тикеты-локализация-KZ/KZ-305-вычитка-kk.md). Positional
# copies of PHRASES / PHRASES_JUNIOR (index N = the kk of PHRASES[cat][N]);
# folded into `text` / `text_junior` = `{"ru": …, "kk": …}` in the STATEMENTS
# loop (per-locale-row storage, KZ-301). Same tone-neutral, one-register
# principle as the `ru` phrasings — no phrasing reads "better written" than
# another (that would bias the forced choice toward wording, not value).
_KK_PHRASES: dict[str, list[str]] = {
    "interest": [
        "Маған шынымен қызық іспен айналысу",
        "Нәтиже үшін емес, өзін-өзі баурап алатын іспен айналысу",
        "Мені шын мәнінде қызықтырған іске бойлау",
        "Білуге әрі сынап көруге қызық нәрсемен жұмыс істеу",
    ],
    "challenge": [
        "Бәрі бірдей бата алмайтын күрделі міндеттерді шешу",
        "Алдымен қолымнан келмейтіндей көрінген іске кірісу",
        "Үнемі жаңаны үйреніп, шеберлікте өсу",
        "Өзімді шынымен қиын міндеттерде сынау",
    ],
    "helping": [
        "Адамдарға пайда келтіріп, оларға көмектесу",
        "Басқалардың өмірін шынымен жеңілдететін нәрсе істеу",
        "Көмекке мұқтаж жандарға пайдалы болу",
        "Басқаларға жақсы болсын деп жұмыс істеу",
    ],
    "freedom": [
        "Бөгденің бақылауынсыз не істеуді әрі қалай істеуді өзім шешу",
        "Қатаң нұсқаусыз, өз қарқыныммен жұмыс істеу",
        "Немен әрі қашан айналысуды өзім таңдау",
        "Жоғарыдан рұқсатсыз шешім қабылдау еркіндігіне ие болу",
    ],
    "money": [
        "Көп ақша табу",
        "Жұмысым үшін жақсы табыс алу",
        "Ешнәрседен өзімді шектемеуге мүмкіндік болу",
        "Ақшаны ойламайтындай етіп табу",
    ],
    "recognition": [
        "Шеберлігім үшін құрметтеп, бағалайтын адам болу",
        "Өз ісінде танымал сарапшы болу",
        "Жақсы істеген ісім үшін мойындау алу",
        "Басқалар мені кәсіби маман деп көруі",
    ],
    "stability": [
        "Бәрі болжамды тұрақты жұмысым болу",
        "Ертең не жыл өткенде не болатынын алдын ала білу",
        "Күтпеген өзгерістер болмайтын жерде жұмыс істеу",
        "Өзім сенетін, берік іске ие болу",
    ],
    "creation": [
        "Өзімдік бір нәрсе — жоба, іс, өнім — жасау",
        "Бір нәрсені нөлден бастап ойлап тауып, құру",
        "Өз ісімді бастау",
        "Өзім жасаған бір нәрсені артымда қалдыру",
    ],
    "teamwork": [
        "Бәрі бір-бірін қолдайтын командада жұмыс істеу",
        "Ортақ істі басқа адамдармен бірге істеу",
        "Мықты әрі тату команданың бір бөлігі болу",
        "Нәтижеге жалғыз емес, бірге жету",
    ],
}

_KK_PHRASES_JUNIOR: dict[str, list[str]] = {
    "interest": [
        "Маған шынымен ұнайтын нәрсені істеу",
        "Баға үшін болмаса да, қызықтыратын іспен айналысу",
        "Қызықтырған іске бас-көзсіз берілу",
        "Қызық көрген нәрсемді сынап көріп, білу",
    ],
    "challenge": [
        "Бәрі шеше бермейтін қиын есептерді шешу",
        "Әуелі тым қиын көрінген нәрсені сынап көру",
        "Үнемі жаңаны үйреніп, жақсара түсу",
        "Өзімді шын қиын тапсырмаларда сынау",
    ],
    "helping": [
        "Адамдарға көмектесіп, пайдалы болу",
        "Басқаларға шынымен көмектесетін нәрсе істеу",
        "Көмек керек жандардың қасында болу",
        "Басқаларға жақсы болсын деп тырысу",
    ],
    "freedom": [
        "Не істеуді әрі қалай істеуді өзім шешу",
        "Қатаң нұсқаусыз, бәрін өз қарқыныммен істеу",
        "Дәл қазір немен айналысуды өзім шешу",
        "Рұқсат сұрамай, өзімше істеу",
    ],
    "money": [
        "Тырысқаным үшін көп жақсы нәрсе алу",
        "Істеген ісім үшін жақсы сыйлық алу",
        "Қалаған нәрсемді өзіме сатып алуға мүмкіндік болу",
        "Ешнәрсеге алаңдамайтындай жеткілікті алу",
    ],
    "recognition": [
        "Не білетінім үшін мені сыйлауы",
        "Өз ісін бәрінен жақсы білетін адам болу",
        "Бір нәрсені жақсы істегенде байқауы",
        "Басқалар менің бұған жүйрік екенімді көруі",
    ],
    "stability": [
        "Өмірім тыныш әрі болжамды болуы",
        "Ертең не болатынын алдын ала білу",
        "Кенеттен өзгерістер болмайтын іспен айналысу",
        "Өзім сенімді болатын іспен айналысу",
    ],
    "creation": [
        "Бұрын болмаған, өзімдікі бір нәрсе жасау",
        "Бір нәрсені нөлден ойлап тауып, жасау",
        "Өзімдікі бір нәрсені құрастыру не жасау",
        "Өзім ойлап тауып жасаған нәрсені артымда қалдыру",
    ],
    "teamwork": [
        "Бәрі бір-бірін қолдайтын командада болу",
        "Ортақ істі басқалармен бірге істеу",
        "Тату команданың бір бөлігі болу",
        "Нәтижеге жалғыз емес, бірге жету",
    ],
}

for _m in (_KK_PHRASES, _KK_PHRASES_JUNIOR):
    assert set(_m) == set(CATEGORIES), f"kk phrase-map category drift: {set(_m) ^ set(CATEGORIES)}"
    assert all(len(v) == 4 for v in _m.values()), "every kk phrase list must have 4 items"

# Locales carried by this bank (ru first — structural source of truth).
LOCALES: tuple[str, ...] = ("ru", "kk")


def _generate_lines() -> list[list[int]]:
    """AG(2,3): 3 vertical lines + 9 sloped lines (3 slopes x 3 intercepts,
    mod 3) = 12 lines of 3 points each, over a 3x3 grid of point indices
    0..8. Every point appears in exactly 4 lines; every pair of points
    co-occurs in exactly 1 line (standard affine-plane property)."""
    lines = [[x * 3 + y for y in range(3)] for x in range(3)]  # vertical
    for slope in range(3):
        for intercept in range(3):
            lines.append([x * 3 + (slope * x + intercept) % 3 for x in range(3)])  # sloped
    return lines


LINES = _generate_lines()
assert len(LINES) == 12

STATEMENTS: list[dict] = []
_seen = {c: 0 for c in CATEGORIES}
for _triplet_index, _line in enumerate(LINES):
    for _order, _point in enumerate(_line):
        _category = CATEGORIES[_point]
        _i = _seen[_category]
        STATEMENTS.append(
            {
                "triplet_index": _triplet_index,
                "order": _order,
                "category": _category,
                "text": {"ru": PHRASES[_category][_i], "kk": _KK_PHRASES[_category][_i]},
                "text_junior": {
                    "ru": PHRASES_JUNIOR[_category][_i],
                    "kk": _KK_PHRASES_JUNIOR[_category][_i],
                },
            }
        )
        _seen[_category] += 1

assert len(STATEMENTS) == 36
assert all(v == 4 for v in _seen.values()), f"unbalanced occurrence counts: {_seen}"
