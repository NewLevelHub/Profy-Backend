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
        STATEMENTS.append(
            {
                "triplet_index": _triplet_index,
                "order": _order,
                "category": _category,
                "text": PHRASES[_category][_seen[_category]],
            }
        )
        _seen[_category] += 1

assert len(STATEMENTS) == 36
assert all(v == 4 for v in _seen.values()), f"unbalanced occurrence counts: {_seen}"
