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

# ── Kazakh (kk) — KZ-305 ──────────────────────────────────────────────────────
#
# LLM-primary translation against docs/i18n.md's glossary; native review pending
# (checklist: ProfOr/Тикеты-локализация-KZ/KZ-305-вычитка-kk.md). Positional
# copy of _CONTENT (same category keys, same 2 facets, same (positive, negative)
# order — the a=positive / b=negative convention scoring relies on is
# preserved). Folded into `text_a` / `text_b` = `{"ru": …, "kk": …}` below.
# Harter frame in kk: "Кейбір балалар …, ал басқалары …".
_KK_CONTENT: dict[str, list[tuple[str, str]]] = {
    "interest": [
        (
            "Кейбір балалар ешкім сұрамаса да, сүйікті ісімен сағаттап айналысуға дайын",
            "Басқа балаларды іс ешкім тапсырмаса, тез жалықтырады",
        ),
        (
            "Кейбір балалар айналысатын істі жай ғана өзіне қызық болғаны үшін таңдағанды ұнатады",
            "Басқа балаларға міндетті болмаса, немен айналысу онша маңызды емес",
        ),
    ],
    "challenge": [
        (
            "Кейбір балалар барлық тапсырманың ішінен әдейі ең күрделісін таңдайды",
            "Басқа балалар мүмкіндік болса, жеңілірек тапсырманы таңдайды",
        ),
        (
            "Кейбір балалар есепті түбегейлі шешкенше бас қатырғанды ұнатады",
            "Басқа балаларға күрделі істі кейінге қалдырып, жеңілірегімен айналысу оңай",
        ),
    ],
    "helping": [
        (
            "Кейбір балалар біреудің қиналғанын көрсе, бірден көмекке асығады",
            "Басқа балалар тек арнайы өтінсе ғана көмектеседі",
        ),
        (
            "Кейбір балалар ренжітілгендерді қорғағанды ұнатады",
            "Басқа балаларға бөгденің дауынан аулақ болу оңай",
        ),
    ],
    "freedom": [
        (
            "Кейбір балалар іске қашан әрі қалай кірісуді ескертусіз өздері шешеді",
            "Басқа балаларға біреу не істеу керегін айтып тұрғаны тынышырақ",
        ),
        (
            "Кейбір балалар бір нәрсені жаңаша істеудің өз жолын тапқанды ұнатады",
            "Басқа балаларға нұсқаулық бойынша қатаң әрекет ету жайлы",
        ),
    ],
    "money": [
        (
            "Кейбір балалар сол үшін сыйлық алатынын білсе, әлдеқайда көп тырысады",
            "Басқа балаларды сыйлық аса қоздырмайды — оларға сыйлықсыз да қызық",
        ),
        (
            "Кейбір балалар бағалы нәрсеге айырбастау үшін ұпай не тиын жинағанды ұнатады",
            "Басқа балаларға жинау онша маңызды емес — үдерістің өзі сыйлықтан маңызды",
        ),
    ],
    "recognition": [
        (
            "Кейбір балалар үлкендер оларды бәрінің көзінше мақтағанын ұнатады",
            "Басқа балалар бәрінің көзінше мақталса, ыңғайсызданады",
        ),
        (
            "Кейбір балаларға айналасындағылар олардың қандай мықты екенін байқағаны маңызды",
            "Басқа балаларға жетістіктеріне назар аудара ма, жоқ па — бәрібір",
        ),
    ],
    "stability": [
        (
            "Кейбір балалар күн бір қалыппен өткенін ұнатады",
            "Басқа балалар өмірде бірдеңе үнемі өзгеріп тұрғанын ұнатады",
        ),
        (
            "Кейбір балаларға әрі қарай не болатынын алдын ала білу маңызды",
            "Басқа балаларға жоспар кенеттен өзгерсе де, қалыпты",
        ),
    ],
    "creation": [
        (
            "Кейбір балалар бұрын ешкім жасамаған нәрсені ойлап тапқанды ұнатады",
            "Басқа балаларға өздеріне дейін ойлап тапқан нәрсені пайдалану оңай",
        ),
        (
            "Кейбір балалар заттарды өз қолымен жасап, құрастырғанды ұнатады",
            "Басқа балаларға бір нәрсені өздері жасау онша қызық емес",
        ),
    ],
    "teamwork": [
        (
            "Кейбір балалар іс тек командамен бірге шыққанын ұнатады",
            "Басқа балалар өздері жалғыз тындырғанды көбірек ұнатады",
        ),
        (
            "Кейбір балаларға тату топтың бір бөлігі екенін сезіну маңызды",
            "Басқа балаларға топтан сәл шеткері жүру жайлы",
        ),
    ],
}

assert set(_KK_CONTENT) == set(CATEGORIES), f"kk content category drift: {set(_KK_CONTENT) ^ set(CATEGORIES)}"
assert all(len(v) == 2 for v in _KK_CONTENT.values()), "every kk category needs 2 facets"

# Locales carried by this bank (ru first — structural source of truth).
LOCALES: tuple[str, ...] = ("ru", "kk")

PAIRS: list[dict] = []
_pair_index = 0
for _category in CATEGORIES:
    for _facet, (_text_a, _text_b) in enumerate(_CONTENT[_category]):
        _kk_a, _kk_b = _KK_CONTENT[_category][_facet]
        _pair_index += 1
        PAIRS.append({
            "pair_index": _pair_index,
            "category_a": _category,
            "category_b": _category,
            "text_a": {"ru": _text_a, "kk": _kk_a},
            "text_b": {"ru": _text_b, "kk": _kk_b},
        })

assert len(PAIRS) == 18, f"expected 18 motivation pairs, got {len(PAIRS)}"
assert all(p["category_a"] == p["category_b"] for p in PAIRS), (
    "every pair must compare the same category's two poles"
)

_appearances = {c: 0 for c in CATEGORIES}
for _p in PAIRS:
    _appearances[_p["category_a"]] += 1
assert all(v == 2 for v in _appearances.values()), f"unbalanced appearance counts: {_appearances}"
