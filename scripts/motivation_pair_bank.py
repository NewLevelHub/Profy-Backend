"""
Motivation pair bank (Harter-format) — pure content + combinatorics, no
scoring logic. Junior/middle's alternative to the 12-triplet MOST/LEAST
mechanic (scripts/motivation_statement_bank.py, which senior keeps using
unchanged): "Some kids like X, but other kids [prefer] Y" — pick a camp,
then rate intensity. Two sequential binary decisions instead of one 3-way
ranking — validated for ages 8-12 as the Structured Alternative Format in
Harter's Self-Perception Profile for Children (SPPC).

Pairing: 9 categories arranged in a circle (same CATEGORIES order as the
triplet bank, reused here — not redefined). Two rotation offsets, k=1 and
k=2, each give 9 distinct unordered pairs (a 9-cycle never revisits a pair
within one offset since 9 is odd and 2k != 0 mod 9 for k in {1,2}) — 18
pairs total, every category appearing in exactly 4 of them (2 per offset).
This does not cover all 36 possible category pairings (only k=1/k=2, not
k=3/k=4) — a pragmatic balance-of-appearances design, not an exhaustive
one, same spirit as the Big Five pair generator's rotating-shift approach
(scripts/question_pairing.py) not needing full domain-pair coverage either.
"""

from scripts.motivation_statement_bank import CATEGORIES

assert len(CATEGORIES) == 9

# category -> its short "camp" description for each side of the sentence.
# Two independent phrasings so the same 18-pair combinatorial layout can
# generate both text_a (category at the "lo" end of an axis) and text_b
# (category at the "hi" end) without literally reusing one shared clause
# for a category regardless of which side it lands on.
_CONTENT: dict[tuple[str, str], tuple[str, str]] = {
    ("interest", "challenge"): (
        "Одни ребята любят заниматься тем, что им просто нравится",
        "Другим ребятам важнее решать трудные задачи, которые не всем по силам",
    ),
    ("challenge", "helping"): (
        "Одни ребята любят пробовать что-то трудное",
        "Другим ребятам важнее помогать тем, кому нужна помощь",
    ),
    ("helping", "freedom"): (
        "Одни ребята любят помогать другим",
        "Другим ребятам важнее самим решать, что и как делать",
    ),
    ("freedom", "money"): (
        "Одни ребята любят делать всё по-своему",
        "Другим ребятам важнее получать что-то хорошее за старания",
    ),
    ("money", "recognition"): (
        "Одни ребята любят получать награду за то, что сделали",
        "Другим ребятам важнее, чтобы их за это уважали",
    ),
    ("recognition", "stability"): (
        "Одни ребята любят, чтобы их хвалили за то, что у них хорошо получается",
        "Другим ребятам важнее, чтобы всё было спокойно и предсказуемо",
    ),
    ("stability", "creation"): (
        "Одни ребята любят, когда всё идёт как обычно",
        "Другим ребятам важнее придумать и сделать что-то новое",
    ),
    ("creation", "teamwork"): (
        "Одни ребята любят создавать что-то своё в одиночку",
        "Другим ребятам важнее делать общее дело вместе с друзьями",
    ),
    ("teamwork", "interest"): (
        "Одни ребята любят быть частью дружной команды",
        "Другим ребятам важнее заниматься тем, что им самим интересно",
    ),
    ("interest", "helping"): (
        "Одни ребята любят заниматься тем, что им нравится",
        "Другим ребятам важнее быть полезными другим",
    ),
    ("challenge", "freedom"): (
        "Одни ребята любят пробовать трудное",
        "Другим ребятам важнее делать всё в своём темпе",
    ),
    ("helping", "money"): (
        "Одни ребята любят помогать другим просто так",
        "Другим ребятам важнее получать что-то за свои старания",
    ),
    ("freedom", "recognition"): (
        "Одни ребята любят решать всё сами",
        "Другим ребятам важнее, чтобы другие видели, что они молодцы",
    ),
    ("money", "stability"): (
        "Одни ребята любят получать награду за старания",
        "Другим ребятам важнее, чтобы всё было спокойно и без сюрпризов",
    ),
    ("recognition", "creation"): (
        "Одни ребята любят, чтобы их замечали за успехи",
        "Другим ребятам важнее придумывать что-то новое",
    ),
    ("stability", "teamwork"): (
        "Одни ребята любят, когда всё привычно",
        "Другим ребятам важнее быть рядом с друзьями в общем деле",
    ),
    ("creation", "interest"): (
        "Одни ребята любят создавать что-то своё",
        "Другим ребятам важнее заниматься тем, что просто нравится",
    ),
    ("teamwork", "challenge"): (
        "Одни ребята любят делать что-то вместе с командой",
        "Другим ребятам важнее справляться с трудными задачами",
    ),
}


def _generate_pairs() -> list[tuple[str, str]]:
    n = len(CATEGORIES)
    pairs: list[tuple[str, str]] = []
    for k in (1, 2):
        for i in range(n):
            pairs.append((CATEGORIES[i], CATEGORIES[(i + k) % n]))
    return pairs


PAIRS: list[dict] = []
for _pair_index, (_cat_a, _cat_b) in enumerate(_generate_pairs(), start=1):
    _text_a, _text_b = _CONTENT[(_cat_a, _cat_b)]
    PAIRS.append({
        "pair_index": _pair_index,
        "category_a": _cat_a,
        "category_b": _cat_b,
        "text_a": _text_a,
        "text_b": _text_b,
    })

assert len(PAIRS) == 18, f"expected 18 motivation pairs, got {len(PAIRS)}"
assert all(p["category_a"] != p["category_b"] for p in PAIRS), "no category may be paired with itself"

_appearances = {c: 0 for c in CATEGORIES}
for _p in PAIRS:
    _appearances[_p["category_a"]] += 1
    _appearances[_p["category_b"]] += 1
assert all(v == 4 for v in _appearances.values()), f"unbalanced appearance counts: {_appearances}"
