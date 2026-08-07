"""
Forced-choice pair generator — TZ_Profi.md §13 bans Likert for junior (6-9),
so junior's whole test is pairs (shown on its own screen, /assessment/pairs).
Middle (10-13) doesn't need a format change (Likert is fine for that age),
but TZ_Profi.md §14 warns that all-one-format tests drive drop-off, so a
subset of middle's questions — everything that only unlocks at middle, not
inherited from junior — is woven into the ordinary Likert flow as
Dilemma/Scenario pairs instead (see buildDisplaySequence.ts on the
frontend). Pairs reference existing `questions` by their bank `order`
(resolved to Question.id at seed time by scripts/seed_question_pairs.py) —
no new response table (a pick is written as two ordinary UserResponse rows,
see app/services/question_pair_service.py).

RIASEC pairing: hexagon-opposite axes (R<->S, I<->E, A<->C) — the standard
forced-choice construction for Holland instruments, since opposite types are
the most discriminating pair to force a choice between. Both junior's and
middle's per-type item counts are symmetric on each axis, so a straight zip
of the two lists (in bank order) covers every item exactly once per tier,
with no leftover.

Big Five pairing: domains have no hexagon-like "opposite" structure, so
pairs are built cross-domain within each pair of adjacent facets (1-2, 3-4,
5-6), rotating which domain matches which by a shift (1, 2, 1 respectively)
so more than one domain-pairing occurs across the three facet-blocks
instead of always matching the same two domains. This is a pragmatic
simplification (ipsative ordering between orthogonal personality domains has
no strong theoretical basis the way RIASEC's hexagon does), not a validated
ipsative Big Five design.

Every pair carries a `content` override: `frame` (a scenario line shown
above the pair), `option_a_text`/`option_b_text` (what each side displays,
independent of the linked Question's own Likert text), and — junior only —
`option_a_icon`/`option_b_icon`. A pair reusing two independent Likert
statements (the original approach) read as "two unrelated questions" in
testing — opposite RIASEC types/Big Five domains are a statistical tendency,
not a moment-to-moment behavioral exclusion — so every junior and middle
pair is hand-written as one situation with two genuinely exclusive actions.
Fields left unset fall back to the linked Question's own short_text/text/
icon (app/services/question_pair_service.py), which no live pair relies on
anymore but keeps old data harmless if a future pair is added without content.
"""

from scripts.bigfive_question_bank import QUESTIONS as _BIGFIVE_QUESTIONS
from scripts.riasec_question_bank import QUESTIONS as _RIASEC_QUESTIONS

_DOMAINS = ["N", "E", "O", "A", "C"]
_RIASEC_AXES = [("R", "S"), ("I", "E"), ("A", "C")]
# (facet_lo, facet_hi, domain_shift) — shift is how many positions forward in
# _DOMAINS the facet_lo domain is matched to find its facet_hi partner.
# Varying the shift (1, 2, 1) across the three blocks spreads pairings
# across more than one pair of domains instead of always matching the same
# two (a fixed shift=1 for all three blocks would only ever pair N<->E,
# E<->O, O<->A, A<->C, C<->N — never e.g. N<->O).
_BIGFIVE_BLOCKS = [(1, 2, 1), (3, 4, 2), (5, 6, 1)]

_Content = dict[str, str | None]


def _riasec_pairs(
    items: list[dict], content: dict[tuple[str, int], _Content], age_tier: str, start_index: int,
) -> tuple[list[dict], int]:
    by_type: dict[str, list[dict]] = {}
    for q in items:
        by_type.setdefault(q["riasec_type"], []).append(q)

    pairs: list[dict] = []
    idx = start_index
    used: set[int] = set()

    for left_type, right_type in _RIASEC_AXES:
        left_items = by_type[left_type]
        right_items = by_type[right_type]
        assert len(left_items) == len(right_items), (
            f"[{age_tier}] {left_type}/{right_type} axis item-count mismatch: "
            f"{len(left_items)} vs {len(right_items)}"
        )
        for pos, (left, right) in enumerate(zip(left_items, right_items), start=1):
            idx += 1
            used.add(left["order"])
            used.add(right["order"])
            c = content.get((left_type, pos), {})
            pairs.append({
                "instrument": "riasec",
                "age_tier": age_tier,
                "pair_index": idx,
                "question_a_order": left["order"],
                "question_b_order": right["order"],
                "frame": c.get("frame"),
                "option_a_text": c.get("option_a_text"),
                "option_b_text": c.get("option_b_text"),
                "option_a_icon": c.get("option_a_icon"),
                "option_b_icon": c.get("option_b_icon"),
            })

    assert used == {q["order"] for q in items}, (
        f"[{age_tier}] not every RIASEC item was used exactly once"
    )
    return pairs, idx


def _bigfive_pairs(
    items: list[dict],
    overrides: dict[tuple[str, int], str],
    content: dict[tuple[str, int], _Content],
    age_tier: str,
    start_index: int,
) -> tuple[list[dict], int]:
    by_domain_facet: dict[tuple[str, int], dict] = {
        (q["bigfive_domain"], q["facet"]): q for q in items
    }
    assert len(by_domain_facet) == 30, f"[{age_tier}] expected 30 Big Five items"

    pairs: list[dict] = []
    idx = start_index
    used: set[tuple[str, int]] = set()

    for facet_lo, facet_hi, shift in _BIGFIVE_BLOCKS:
        for d_idx, domain_lo in enumerate(_DOMAINS):
            override_domain = overrides.get((domain_lo, facet_lo))
            domain_hi = override_domain or _DOMAINS[(d_idx + shift) % 5]
            assert domain_lo != domain_hi
            left = by_domain_facet[(domain_lo, facet_lo)]
            right = by_domain_facet[(domain_hi, facet_hi)]
            used.add((domain_lo, facet_lo))
            used.add((domain_hi, facet_hi))
            idx += 1
            c = content.get((domain_lo, facet_lo), {})
            pairs.append({
                "instrument": "big_five",
                "age_tier": age_tier,
                "pair_index": idx,
                "question_a_order": left["order"],
                "question_b_order": right["order"],
                "frame": c.get("frame"),
                "option_a_text": c.get("option_a_text"),
                "option_b_text": c.get("option_b_text"),
                "option_a_icon": c.get("option_a_icon"),
                "option_b_icon": c.get("option_b_icon"),
            })

    assert used == set(by_domain_facet.keys()), (
        f"[{age_tier}] not every Big Five item was used exactly once"
    )
    return pairs, idx


# ═══════════════════════ Junior (whole test is pairs) ═══════════════════════

_riasec_junior = [q for q in _RIASEC_QUESTIONS if q["age_tier"] == "junior"]
_bigfive_junior = [q for q in _BIGFIVE_QUESTIONS if q["age_tier"] == "junior"]

assert len(_riasec_junior) == 38, f"expected 38 junior RIASEC items, got {len(_riasec_junior)}"
assert len(_bigfive_junior) == 30, f"expected 30 junior Big Five items, got {len(_bigfive_junior)}"

# Every junior pair is a hand-written situational dilemma, same fix as
# middle's (see _MIDDLE_RIASEC_CONTENT) — the old mechanical zip of two
# independent Likert items read as "two unrelated questions" instead of a
# real choice. (type, 1-based position within that type's junior items) ->
# content. Short child-friendly phrasing + a fresh icon per option, since
# TZ_Profi.md §13 requires icons for junior's format and the rewritten
# action may no longer match the linked Question's original icon.
_JUNIOR_RIASEC_CONTENT: dict[tuple[str, int], _Content] = {
    # R vs S
    ("R", 1): {
        "frame": "Во дворе сломался самокат, а друг зовёт играть в салки. Время есть только на одно.",
        "option_a_text": "Чинить самокат", "option_a_icon": "🔧",
        "option_b_text": "Играть в салки", "option_b_icon": "🏃",
    },
    ("R", 2): {
        "frame": "На уроке труда можно смастерить скворечник, или помочь соседу по парте, у которого не получается.",
        "option_a_text": "Смастерить скворечник", "option_a_icon": "🔨",
        "option_b_text": "Помочь соседу", "option_b_icon": "🤗",
    },
    ("R", 3): {
        "frame": "После школы можно разобрать старую игрушку дома, или пойти в гости к другу, который давно зовёт.",
        "option_a_text": "Разобрать игрушку", "option_a_icon": "⚙️",
        "option_b_text": "Пойти в гости", "option_b_icon": "👋",
    },
    ("R", 4): {
        "frame": "На перемене можно тихо посидеть в сторонке, или подойти познакомиться с новеньким в классе.",
        "option_a_text": "Посидеть в сторонке", "option_a_icon": "🤫",
        "option_b_text": "Познакомиться с новеньким", "option_b_icon": "👋",
    },
    ("R", 5): {
        "frame": "Дома сломался пульт от телевизора, а младший братик просит поиграть с ним прямо сейчас.",
        "option_a_text": "Починить пульт", "option_a_icon": "🔧",
        "option_b_text": "Поиграть с братиком", "option_b_icon": "🤗",
    },
    ("R", 6): {
        "frame": "На физкультуре можно построить полосу препятствий, или подбодрить того, кто боится её пройти.",
        "option_a_text": "Строить полосу препятствий", "option_a_icon": "🏗️",
        "option_b_text": "Подбодрить друга", "option_b_icon": "💗",
    },
    # I vs E
    ("I", 1): {
        "frame": "На занятии можно разгадывать головоломку самому, или собрать вокруг себя ребят и придумать общую игру.",
        "option_a_text": "Разгадывать головоломку", "option_a_icon": "🧩",
        "option_b_text": "Собрать всех на игру", "option_b_icon": "⚡",
    },
    ("I", 2): {
        "frame": "На кружке можно разобраться, как устроен конструктор, или показать всем, что ты уже придумал.",
        "option_a_text": "Разобраться в конструкторе", "option_a_icon": "🔍",
        "option_b_text": "Показать всем", "option_b_icon": "📢",
    },
    ("I", 3): {
        "frame": "В научном уголке можно провести опыт самому, или рассказать всему классу, что получилось.",
        "option_a_text": "Провести опыт", "option_a_icon": "🧪",
        "option_b_text": "Рассказать классу", "option_b_icon": "🗯️",
    },
    ("I", 4): {
        "frame": "На перемене можно заметить, что не так в рисунке, или предложить всем сыграть в новую игру.",
        "option_a_text": "Заметить, что не так", "option_a_icon": "🔎",
        "option_b_text": "Предложить новую игру", "option_b_icon": "🎉",
    },
    ("I", 5): {
        "frame": "После уроков можно почитать про что-то сложное и интересное, или пойти на что-то рискованное во дворе.",
        "option_a_text": "Почитать про интересное", "option_a_icon": "📚",
        "option_b_text": "Попробовать рискованное", "option_b_icon": "🎢",
    },
    ("I", 6): {
        "frame": "Перед контрольной можно сначала спокойно подумать, или сразу поднять руку и ответить первым.",
        "option_a_text": "Сначала подумать", "option_a_icon": "🤔",
        "option_b_text": "Ответить первым", "option_b_icon": "🏆",
    },
    # A vs C
    ("A", 1): {
        "frame": "На рисовании можно придумать что-то своё необычное, или разложить карандаши по цветам, как учили.",
        "option_a_text": "Придумать необычное", "option_a_icon": "🎨",
        "option_b_text": "Разложить по местам", "option_b_icon": "🗂️",
    },
    ("A", 2): {
        "frame": "Можно сочинить свою историю, или аккуратно переписать текст без единой ошибки.",
        "option_a_text": "Сочинить историю", "option_a_icon": "📖",
        "option_b_text": "Быть аккуратным", "option_b_icon": "✅",
    },
    ("A", 3): {
        "frame": "На математике можно посчитать пример необычным способом, или решить его точно по образцу.",
        "option_a_text": "Решить по-своему", "option_a_icon": "💡",
        "option_b_text": "Считать по образцу", "option_b_icon": "🔢",
    },
    ("A", 4): {
        "frame": "Можно сделать поделку не как у всех, или сделать её строго по инструкции.",
        "option_a_text": "Сделать не как все", "option_a_icon": "🌀",
        "option_b_text": "Сделать по инструкции", "option_b_icon": "📋",
    },
    ("A", 5): {
        "frame": "На музыке можно придумать свою мелодию, или доиграть заданную пьесу до конца.",
        "option_a_text": "Придумать мелодию", "option_a_icon": "🎵",
        "option_b_text": "Доиграть до конца", "option_b_icon": "✔️",
    },
    ("A", 6): {
        "frame": "Можно рисовать, что хочется, весь урок, или успеть за урок сделать всё, что задали.",
        "option_a_text": "Рисовать, что хочется", "option_a_icon": "🖌️",
        "option_b_text": "Успеть всё сделать", "option_b_icon": "⏱️",
    },
    ("A", 7): {
        "frame": "На школьном празднике можно выступить ярко и заметно, или точно следовать правилам конкурса.",
        "option_a_text": "Выступить ярко", "option_a_icon": "✨",
        "option_b_text": "Играть по правилам", "option_b_icon": "📏",
    },
}

# Manual override: the shift-based match for (O,facet1)/(A,facet2) paired
# "У меня богатая фантазия" against "Использую других для своей выгоды" —
# two orthogonal, tonally mismatched items. Changing the block's shift would
# only relocate the same awkward item onto a different partner, not remove
# it, so instead we locally swap O1's and C1's targets within this one block
# (both stay within facet_hi=2, so every item is still used exactly once).
_JUNIOR_BIGFIVE_OVERRIDES: dict[tuple[str, int], str] = {
    ("O", 1): "N",
    ("C", 1): "A",
}

# (domain, facet) of the "lo" side -> content. Covers all 15 junior Big
# Five pairs — same hand-written-scenario treatment as RIASEC above. A few
# of these pair a calm/considered reaction against an impulsive/negative one
# (anger, giving up, arrogance) rather than two equally "nice" options —
# that mirrors the underlying reverse-keyed items (Keyed.minus) they're
# built from, not a new bias: a real kid dilemma sometimes is "push through
# or get frustrated and quit", not always two virtues.
_JUNIOR_BIGFIVE_CONTENT: dict[tuple[str, int], _Content] = {
    ("N", 1): {  # N vs E
        "frame": "Дома тихо и спокойно, а во дворе шумный праздник с музыкой.",
        "option_a_text": "Остаться в тихом месте", "option_a_icon": "🏠",
        "option_b_text": "Пойти на шумный праздник", "option_b_icon": "🎉",
    },
    ("E", 1): {  # E vs O
        "frame": "В новом кружке можно сразу подойти и познакомиться с ребятами, или рассмотреть красивые картины на стене.",
        "option_a_text": "Познакомиться с ребятами", "option_a_icon": "👋",
        "option_b_text": "Рассмотреть картины", "option_b_icon": "🎨",
    },
    ("O", 1): {  # O vs N (override target)
        "frame": "Рисунок не получается так, как хотелось.",
        "option_a_text": "Придумать что-то новое", "option_a_icon": "🌈",
        "option_b_text": "Разозлиться и бросить", "option_b_icon": "😠",
    },
    ("A", 1): {  # A vs C
        "frame": "Друг просит помочь ему прямо сейчас разобраться со сложным заданием, а в комнате давно пора убраться — на всё сразу времени не хватит.",
        "option_a_text": "Помочь другу с заданием", "option_a_icon": "🤝",
        "option_b_text": "Убрать в комнате", "option_b_icon": "🧹",
    },
    ("C", 1): {  # C vs A (override target)
        "frame": "В команде осталась сложная часть проекта, а лёгкая уже почти готова.",
        "option_a_text": "Взять сложную часть и довести до конца", "option_a_icon": "✅",
        "option_b_text": "Присоединиться к лёгкой части", "option_b_icon": "😏",
    },
    ("N", 3): {  # N vs O
        "frame": "После неудачи на контрольной можно спокойно посидеть одному и прийти в себя, или сразу пойти на кружок, чтобы отвлечься новым делом.",
        "option_a_text": "Побыть одному", "option_a_icon": "😢",
        "option_b_text": "Пойти отвлечься новым делом", "option_b_icon": "🔀",
    },
    ("E", 3): {  # E vs C (override target)
        "frame": "Во дворе собралась компания: одни распределяют роли для игры, другие уже дурачатся и толкаются в шутку.",
        "option_a_text": "Взять себе главную роль", "option_a_icon": "🙋",
        "option_b_text": "Присоединиться к дурачеству", "option_b_icon": "🤼",
    },
    ("O", 3): {  # O vs A (override target)
        "frame": "Досмотрел грустный фильм, а его финал никак не идёт из головы — но домашку ещё нужно успеть доделать до вечера.",
        "option_a_text": "Ещё погрустить о фильме", "option_a_icon": "💗",
        "option_b_text": "Сразу взяться за домашку", "option_b_icon": "💼",
    },
    ("A", 3): {  # A vs N
        "frame": "Новенький в классе один на перемене.",
        "option_a_text": "Подойти и помочь освоиться", "option_a_icon": "🤗",
        "option_b_text": "Пройти мимо", "option_b_icon": "🚶",
    },
    ("C", 3): {  # C vs E
        "frame": "Ты пообещал другу помочь после школы, а тут набралось ещё много других дел.",
        "option_a_text": "Сдержать обещание другу", "option_a_icon": "🤞",
        "option_b_text": "Заняться всеми делами сразу", "option_b_icon": "🏃",
    },
    ("N", 5): {  # N vs E
        "frame": "На дне рождения так весело, что уже пора уходить, а останавливаться не хочется.",
        "option_a_text": "Продолжать веселиться, забыв про время", "option_a_icon": "🛑",
        "option_b_text": "Вовремя остановиться и попрощаться", "option_b_icon": "☀️",
    },
    ("E", 5): {  # E vs O
        "frame": "В лагере можно записаться в поход с элементами приключений, или пойти на встречу с путешественником, который расскажет про жизнь в разных странах.",
        "option_a_text": "Пойти в поход-приключение", "option_a_icon": "🎢",
        "option_b_text": "Пойти на встречу с путешественником", "option_b_icon": "🌍",
    },
    ("O", 5): {  # O vs A
        "frame": "Только устроился поудобнее со сложной, но захватывающей книгой — и тут пишет друг: у него не очень настроение, и он зовёт поболтать.",
        "option_a_text": "Дочитать книгу", "option_a_icon": "📖",
        "option_b_text": "Поболтать с другом", "option_b_icon": "💔",
    },
    ("A", 5): {  # A vs C
        "frame": "На соревновании ты выиграл.",
        "option_a_text": "Сказать, что был лучше всех", "option_a_icon": "😤",
        "option_b_text": "Сказать, что все молодцы", "option_b_icon": "🤝",
    },
    ("C", 5): {  # C vs N
        "frame": "Внезапно поменялись планы на день.",
        "option_a_text": "Быстро составить новый план", "option_a_icon": "🗺️",
        "option_b_text": "Всё делать на ходу", "option_b_icon": "🤹",
    },
}

_junior_riasec_pairs, _idx = _riasec_pairs(_riasec_junior, _JUNIOR_RIASEC_CONTENT, "junior", 0)
_junior_bigfive_pairs, _idx = _bigfive_pairs(
    _bigfive_junior, _JUNIOR_BIGFIVE_OVERRIDES, _JUNIOR_BIGFIVE_CONTENT, "junior", _idx
)

assert len(_junior_riasec_pairs) == 19, f"expected 19 junior RIASEC pairs, got {len(_junior_riasec_pairs)}"
assert len(_junior_bigfive_pairs) == 15, f"expected 15 junior Big Five pairs, got {len(_junior_bigfive_pairs)}"
assert _idx == 34, f"expected 34 junior pairs total, got {_idx}"

# ══════════════════ Middle (subset woven into the Likert flow) ══════════════

_riasec_middle = [q for q in _RIASEC_QUESTIONS if q["age_tier"] == "middle"]
_bigfive_middle = [q for q in _BIGFIVE_QUESTIONS if q["age_tier"] == "middle"]

assert len(_riasec_middle) == 36, f"expected 36 middle-only RIASEC items, got {len(_riasec_middle)}"
assert len(_bigfive_middle) == 30, f"expected 30 middle-only Big Five items, got {len(_bigfive_middle)}"

# Every middle pair is a hand-written situational dilemma: one scenario,
# two genuinely exclusive actions (can't do both — not enough time, or one
# choice precludes the other). Earlier version just zipped two independent
# Likert statements from "opposite" types/domains — statistically opposite
# on average, but not behaviorally exclusive in the moment, so it read as
# two unrelated questions instead of a real choice (user testing feedback).
# (type, 1-based position within that type's middle-only items) -> content
_MIDDLE_RIASEC_CONTENT: dict[tuple[str, int], _Content] = {
    # R vs S
    ("R", 1): {
        "frame": "Сосед просит помочь починить велосипед, а друг заодно зовёт погулять во дворе.",
        "option_a_text": "Чинить велосипед", "option_b_text": "Пойти погулять с другом",
    },
    ("R", 2): {
        "frame": "На субботнике можно записаться чинить забор или организовывать чаепитие для всех после работы.",
        "option_a_text": "Чинить забор", "option_b_text": "Организовать чаепитие",
    },
    ("R", 3): {
        "frame": "В лагере один отряд идёт строить шалаш в лесу, другой — играть в командные игры на поляне.",
        "option_a_text": "Строить шалаш", "option_b_text": "Играть с командой",
    },
    ("R", 4): {
        "frame": "На выходных можно разобрать старый компьютер дома или пойти в гости к однокласснику, который зовёт давно.",
        "option_a_text": "Разобрать компьютер", "option_b_text": "Пойти в гости",
    },
    ("R", 5): {
        "frame": "На перемене учитель просит помочь разобраться с компьютером, а новенький в классе не может ни с кем познакомиться.",
        "option_a_text": "Помочь учителю с компьютером", "option_b_text": "Помочь новенькому освоиться",
    },
    ("R", 6): {
        "frame": "На выходных можно помочь по хозяйству, или поехать с семьёй в гости к родственникам.",
        "option_a_text": "Помочь по хозяйству", "option_b_text": "Поехать в гости",
    },
    # I vs E
    ("I", 1): {
        "frame": "В научном клубе набирают: одни разбираются в сложной задаче сами, другие готовят презентацию для школы.",
        "option_a_text": "Разбираться в задаче", "option_b_text": "Готовить презентацию",
    },
    ("I", 2): {
        "frame": "На проекте можно глубоко изучить тему самому или взять на себя выступление перед классом.",
        "option_a_text": "Изучать тему", "option_b_text": "Выступать перед классом",
    },
    ("I", 3): {
        "frame": "В команде на школьной олимпиаде можно взять на себя самую сложную задачу, или стать капитаном и вести всю команду.",
        "option_a_text": "Решать сложную задачу", "option_b_text": "Стать капитаном команды",
    },
    ("I", 4): {
        "frame": "На кружке робототехники: один разбирается в программе робота, другой представляет робота жюри.",
        "option_a_text": "Разбираться в программе", "option_b_text": "Представлять жюри",
    },
    ("I", 5): {
        "frame": "На перемене можно доспорить с другом о том, как устроена головоломка, или собрать класс на игру, которую ты придумал.",
        "option_a_text": "Разобраться в головоломке", "option_b_text": "Собрать класс на игру",
    },
    ("I", 6): {
        "frame": "В команде на конкурсе можно взять на себя анализ данных, или сразу предложить свою смелую идею.",
        "option_a_text": "Анализировать данные", "option_b_text": "Предложить смелую идею",
    },
    # A vs C
    ("A", 1): {
        "frame": "На технологии можно придумать что-то необычное самому или аккуратно сделать поделку строго по инструкции.",
        "option_a_text": "Придумать необычное", "option_b_text": "Сделать по инструкции",
    },
    ("A", 2): {
        "frame": "Готовите классный уголок: один рисует яркий плакат от руки, другой расставляет всё по чёткому плану.",
        "option_a_text": "Рисовать плакат", "option_b_text": "Расставлять по плану",
    },
    ("A", 3): {
        "frame": "После уроков можно дорисовать свой рисунок, или переписать набело конспект по истории.",
        "option_a_text": "Дорисовать рисунок", "option_b_text": "Переписать конспект набело",
    },
    ("A", 4): {
        "frame": "Доклад можно оформить необычно, по-своему, или сделать по образцу, который дал учитель.",
        "option_a_text": "Оформить по-своему", "option_b_text": "Сделать по образцу",
    },
    ("A", 5): {
        "frame": "На кружке можно сочинить свою историю без правил, или составить подробный план выступления по пунктам.",
        "option_a_text": "Сочинить историю", "option_b_text": "Составить план по пунктам",
    },
    ("A", 6): {
        "frame": "В свободный день можно порисовать то, что придумалось, или составить чёткий план дел на неделю.",
        "option_a_text": "Порисовать", "option_b_text": "Составить план на неделю",
    },
}

# Same awkward-shift-pairing issue as junior's block, same fix: locally swap
# two targets within the facet3/4 block instead of relocating the mismatch.
_MIDDLE_BIGFIVE_OVERRIDES: dict[tuple[str, int], str] = {
    ("O", 1): "N",
    ("C", 1): "A",
    ("E", 3): "C",
    ("O", 3): "A",
}

# (domain, facet) of the "lo" side -> content. Covers all 15 middle Big Five
# pairs (see class docstring — every middle pair is a hand-written scenario).
_MIDDLE_BIGFIVE_CONTENT: dict[tuple[str, int], _Content] = {
    ("N", 1): {  # N vs E
        "frame": "Завтра контрольная, а вечером друзья зовут в шумную компанию.",
        "option_a_text": "Остаться и подготовиться дома", "option_b_text": "Пойти к друзьям повеселиться",
    },
    ("E", 1): {  # E vs O
        "frame": "Ты переходишь в новую школу. На перемене есть время только на одно.",
        "option_a_text": "Подойти и познакомиться с новыми ребятами", "option_b_text": "Присмотреться, что тут интересного",
    },
    ("O", 1): {  # O vs N (override target)
        "frame": "На рисовании можно придумать что-то фантастическое, или переживать, что рисунок получится не так, как надо.",
        "option_a_text": "Придумать фантастическое", "option_b_text": "Переживать за рисунок",
    },
    ("A", 1): {  # A vs C
        "frame": "У друга сломалась любимая вещь, а у тебя незакрытое домашнее задание — время есть на одно.",
        "option_a_text": "Помочь другу", "option_b_text": "Доделать задание",
    },
    ("C", 1): {  # C vs A (override target)
        "frame": "На субботнике можно довести до конца начатое дело или сразу пойти помочь тому, кому явно тяжелее.",
        "option_a_text": "Довести своё дело до конца", "option_b_text": "Помочь тому, кому тяжелее",
    },
    ("N", 3): {  # N vs O
        "frame": "Перед трудным экзаменом можно ещё раз перепроверить всё, что уже выучил, или попробовать разобраться в теме с другой стороны.",
        "option_a_text": "Перепроверить всё", "option_b_text": "Взглянуть по-новому",
    },
    ("E", 3): {  # E vs C (override target)
        "frame": "Учитель поручил группе важное задание.",
        "option_a_text": "Взять на себя роль главного", "option_b_text": "Сделать самую сложную часть лучше всех",
    },
    ("O", 3): {  # O vs A (override target)
        "frame": "На литературе можно придумать свою версию концовки истории, или подробно описать, что чувствовал главный герой.",
        "option_a_text": "Придумать другой конец", "option_b_text": "Описать чувства героя",
    },
    ("A", 3): {  # A vs N
        "frame": "У одноклассника не получается в игре, и все смотрят на него.",
        "option_a_text": "Подбодрить его при всех", "option_b_text": "Отойти в сторону",
    },
    ("C", 3): {  # C vs E
        "frame": "После уроков можно спокойно разобрать рюкзак и записи или побежать во двор к шумной компании.",
        "option_a_text": "Разобрать рюкзак", "option_b_text": "Побежать к друзьям",
    },
    ("N", 5): {  # N vs E
        "frame": "Вечером дома тихо, а на улице друзья зовут на шумные приключения.",
        "option_a_text": "Остаться дома, где спокойно", "option_b_text": "Пойти на приключения",
    },
    ("E", 5): {  # E vs O
        "frame": "Свободный вечер на каникулах — можно пойти туда, где будет весело и много новых знакомств, или остаться дома с книгой, которая затягивает так, что не оторваться.",
        "option_a_text": "Пойти, где весело", "option_b_text": "Остаться с книгой",
    },
    ("O", 5): {  # O vs A
        "frame": "На групповом проекте у тебя есть необычная идея, а одноклассник просит выбрать что-то попроще, чтобы успевать вместе с тобой.",
        "option_a_text": "Предложить свою идею", "option_b_text": "Выбрать простое ради товарища",
    },
    ("A", 5): {  # A vs C
        "frame": "У друга не получается задача, а у тебя самого есть незакрытое давнее дело.",
        "option_a_text": "Помочь другу", "option_b_text": "Закрыть своё дело",
    },
    ("C", 5): {  # C vs N
        "frame": "Планы на выходные внезапно поменялись.",
        "option_a_text": "Быстро составить новый чёткий план", "option_b_text": "Немного растеряться, прежде чем решить",
    },
}

_middle_riasec_pairs, _idx = _riasec_pairs(_riasec_middle, _MIDDLE_RIASEC_CONTENT, "middle", _idx)
_middle_bigfive_pairs, _idx = _bigfive_pairs(
    _bigfive_middle, _MIDDLE_BIGFIVE_OVERRIDES, _MIDDLE_BIGFIVE_CONTENT, "middle", _idx
)

assert len(_middle_riasec_pairs) == 18, f"expected 18 middle RIASEC pairs, got {len(_middle_riasec_pairs)}"
assert len(_middle_bigfive_pairs) == 15, f"expected 15 middle Big Five pairs, got {len(_middle_bigfive_pairs)}"
assert _idx == 67, f"expected 34+33=67 pairs total, got {_idx}"

_middle_all = _middle_riasec_pairs + _middle_bigfive_pairs
assert all(p["frame"] and p["option_a_text"] and p["option_b_text"] for p in _middle_all), (
    "every middle pair must be a fully hand-written scenario (frame + both option texts)"
)

_junior_all = _junior_riasec_pairs + _junior_bigfive_pairs
assert all(
    p["frame"] and p["option_a_text"] and p["option_b_text"]
    and p["option_a_icon"] and p["option_b_icon"]
    for p in _junior_all
), "every junior pair must be a fully hand-written scenario (frame + both option texts + icons)"

PAIRS: list[dict] = [
    *_junior_riasec_pairs, *_junior_bigfive_pairs,
    *_middle_riasec_pairs, *_middle_bigfive_pairs,
]
