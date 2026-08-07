"""
Motivation pair bank (Harter-format) — pure content + combinatorics, no
scoring logic. Junior/middle's alternative to the 12-triplet MOST/LEAST
mechanic (scripts/motivation_statement_bank.py, which senior keeps using
unchanged): "Some kids [positive pole], but other kids [negative pole]" of
the SAME motivational category — pick a pole, then rate intensity. This is
genuine Harter Self-Perception Profile for Children (SPPC) Structured
Alternative Format: real Harter items compare high vs low expression of ONE
construct, not two different constructs against each other (an earlier
version of this bank cross-paired different categories — interest vs
challenge, helping vs freedom, etc. — which is an ipsative Thurstonian
design, not actually Harter's own item structure, and forced artificial
trade-offs between motives that aren't mutually exclusive in real kids).

Each category gets exactly 2 items (18 pairs total, same test length as
before), covering two distinct concrete facets of that motive so the two
items don't read as literal repeats. `category_a` always equals
`category_b` on every pair — `text_a` is the positive/high-pole phrasing,
`text_b` the negative/low-pole phrasing (this a/b = positive/negative
convention is relied on by app/services/motivation_pair_service.py's
scoring, not re-derived at runtime).
"""

from scripts.motivation_statement_bank import CATEGORIES

assert len(CATEGORIES) == 9

# category -> [(positive, negative), (positive, negative)] — two distinct
# facets of the same motive, each as a high-pole vs low-pole pair.
_CONTENT: dict[str, list[tuple[str, str]]] = {
    "interest": [
        (
            "Одни ребята готовы часами заниматься любимым делом, даже если никто не просит",
            "Других ребят дело быстро перестаёт увлекать, если его никто не задавал",
        ),
        (
            "Одним ребятам нравится выбирать занятие просто потому, что оно им самим интересно",
            "Другим ребятам не так важно, чем заниматься, если это не обязательно",
        ),
    ],
    "challenge": [
        (
            "Одни ребята специально выбирают самое сложное задание из всех",
            "Другие ребята выбирают задание попроще, если есть такая возможность",
        ),
        (
            "Одним ребятам нравится биться над задачей, пока не разберутся до конца",
            "Другим ребятам проще отложить сложное дело и заняться чем-то полегче",
        ),
    ],
    "helping": [
        (
            "Одни ребята сразу спешат на помощь, если видят, что кому-то трудно",
            "Другие ребята помогают, только если их специально попросят",
        ),
        (
            "Одним ребятам нравится заступаться за тех, кого обижают",
            "Другим ребятам проще остаться в стороне от чужих ссор",
        ),
    ],
    "freedom": [
        (
            "Одни ребята сами решают, когда и как взяться за дело, без напоминаний",
            "Другим ребятам спокойнее, когда кто-то подсказывает, что делать",
        ),
        (
            "Одним ребятам нравится находить свой способ сделать что-то по-новому",
            "Другим ребятам комфортнее действовать строго по инструкции",
        ),
    ],
    "money": [
        (
            "Одни ребята стараются намного больше, если знают, что получат за это подарок",
            "Других ребят награда почти не подстёгивает — им интересно и без неё",
        ),
        (
            "Одним ребятам нравится копить очки или монетки, чтобы обменять на что-то ценное",
            "Другим ребятам не так важно копить — сам процесс важнее приза",
        ),
    ],
    "recognition": [
        (
            "Одни ребята любят, когда взрослые хвалят их перед всеми",
            "Другим ребятам неловко, когда их хвалят при всех",
        ),
        (
            "Одним ребятам важно, чтобы окружающие заметили, какие они молодцы",
            "Другим ребятам всё равно, обратят ли внимание на их успехи",
        ),
    ],
    "stability": [
        (
            "Одни ребята любят, когда день идёт по одному и тому же порядку",
            "Другим ребятам нравится, когда что-то в жизни постоянно меняется",
        ),
        (
            "Одним ребятам важно заранее знать, что будет происходить дальше",
            "Другим ребятам норм, даже если планы неожиданно меняются",
        ),
    ],
    "creation": [
        (
            "Одни ребята любят придумывать то, чего раньше никто не делал",
            "Другим ребятам проще пользоваться тем, что уже придумали до них",
        ),
        (
            "Одним ребятам нравится мастерить и создавать вещи своими руками",
            "Другим ребятам не так интересно создавать что-то самим",
        ),
    ],
    "teamwork": [
        (
            "Одни ребята любят, когда дело получается только вместе с командой",
            "Другим ребятам больше нравится справляться самому, в одиночку",
        ),
        (
            "Одним ребятам важно чувствовать себя частью дружной компании",
            "Другим ребятам комфортнее держаться немного в стороне от компании",
        ),
    ],
}

assert set(_CONTENT.keys()) == set(CATEGORIES)
assert all(len(items) == 2 for items in _CONTENT.values())

PAIRS: list[dict] = []
_pair_index = 0
for _category in CATEGORIES:
    for _text_a, _text_b in _CONTENT[_category]:
        _pair_index += 1
        PAIRS.append({
            "pair_index": _pair_index,
            "category_a": _category,
            "category_b": _category,
            "text_a": _text_a,
            "text_b": _text_b,
        })

assert len(PAIRS) == 18, f"expected 18 motivation pairs, got {len(PAIRS)}"
assert all(p["category_a"] == p["category_b"] for p in PAIRS), (
    "every pair must compare the same category's two poles"
)

_appearances = {c: 0 for c in CATEGORIES}
for _p in PAIRS:
    _appearances[_p["category_a"]] += 1
assert all(v == 2 for v in _appearances.values()), f"unbalanced appearance counts: {_appearances}"
