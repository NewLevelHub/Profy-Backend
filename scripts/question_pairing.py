"""
Forced-choice pair generator for the junior (6-9) format — TZ_Profi.md §13
bans Likert for this age branch. Pairs reference existing junior-tier
`questions` by their bank `order` (resolved to Question.id at seed time by
scripts/seed_question_pairs.py) — no new statement content, no new response
table (a pick is written as two ordinary UserResponse rows, see
app/services/question_pair_service.py).

RIASEC pairing: hexagon-opposite axes (R<->S, I<->E, A<->C) — the standard
forced-choice construction for Holland instruments, since opposite types are
the most discriminating pair to force a choice between. Junior per-type
counts are symmetric on each axis (R=S=6, I=E=6, A=C=7), so a straight zip
of the two lists (in bank order) covers every junior RIASEC item exactly
once, with no leftover.

Big Five pairing: domains have no hexagon-like "opposite" structure, so
pairs are built cross-domain within each pair of adjacent facets (1-2, 3-4,
5-6), rotating which domain matches which by a shift (1, 2, 1 respectively)
so more than one domain-pairing occurs across the three facet-blocks
instead of always matching the same two domains. This is a pragmatic
simplification (ipsative ordering between orthogonal personality domains has
no strong theoretical basis the way RIASEC's hexagon does), not a validated
ipsative Big Five design — junior Big Five results should be read as a
coarser signal than middle/senior's direct Likert.

Every pair may optionally carry a `frame` — a short scenario line shown
above the pair, so not all 34 screens look identical (TZ_Profi.md §14:
repeated question formats are the main cause of drop-off).
"""

from scripts.bigfive_question_bank import QUESTIONS as _BIGFIVE_QUESTIONS
from scripts.riasec_question_bank import QUESTIONS as _RIASEC_QUESTIONS

_riasec_junior = [q for q in _RIASEC_QUESTIONS if q["age_tier"] == "junior"]
_bigfive_junior = [q for q in _BIGFIVE_QUESTIONS if q["age_tier"] == "junior"]

assert len(_riasec_junior) == 38, f"expected 38 junior RIASEC items, got {len(_riasec_junior)}"
assert len(_bigfive_junior) == 30, f"expected 30 junior Big Five items, got {len(_bigfive_junior)}"

# --- RIASEC: hexagon-opposite axes ---------------------------------------

_RIASEC_AXES = [("R", "S"), ("I", "E"), ("A", "C")]

_riasec_by_type: dict[str, list[dict]] = {}
for _q in _riasec_junior:
    _riasec_by_type.setdefault(_q["riasec_type"], []).append(_q)

# (type, 1-based position within that type's junior items) -> scenario intro
RIASEC_FRAMES: dict[tuple[str, int], str] = {
    ("R", 3): "Представь: во дворе твой друг с кем-то поссорился, а ещё у тебя сломался велосипед. Что бы ты сделал в первую очередь?",
    ("I", 1): "Ты оказался в незнакомом месте. Что бы ты сделал?",
    ("I", 5): "На каникулах можно заняться чем угодно. Что тебе ближе?",
    ("A", 3): "В игре нужно быстро решить головоломку. Что тебе ближе?",
    ("A", 7): "На школьном празднике все готовят выступление. Что тебе ближе?",
}

PAIRS: list[dict] = []
_pair_index = 0
_used_riasec_orders: set[int] = set()

for _left_type, _right_type in _RIASEC_AXES:
    _left_items = _riasec_by_type[_left_type]
    _right_items = _riasec_by_type[_right_type]
    assert len(_left_items) == len(_right_items), (
        f"{_left_type}/{_right_type} axis item-count mismatch: "
        f"{len(_left_items)} vs {len(_right_items)}"
    )
    for _pos, (_left, _right) in enumerate(zip(_left_items, _right_items), start=1):
        _pair_index += 1
        _used_riasec_orders.add(_left["order"])
        _used_riasec_orders.add(_right["order"])
        PAIRS.append({
            "instrument": "riasec",
            "pair_index": _pair_index,
            "question_a_order": _left["order"],
            "question_b_order": _right["order"],
            "frame": RIASEC_FRAMES.get((_left_type, _pos)),
        })

assert _pair_index == 19, f"expected 19 RIASEC pairs, got {_pair_index}"
assert _used_riasec_orders == {q["order"] for q in _riasec_junior}, (
    "not every junior RIASEC item was used exactly once"
)

# --- Big Five: cross-domain, rotating shift per facet-pair block ---------

_DOMAINS = ["N", "E", "O", "A", "C"]
_bigfive_by_domain_facet: dict[tuple[str, int], dict] = {
    (q["bigfive_domain"], q["facet"]): q for q in _bigfive_junior
}
assert len(_bigfive_by_domain_facet) == 30

# (facet_lo, facet_hi, domain_shift) — shift is how many positions forward
# in _DOMAINS the facet_lo domain is matched to find its facet_hi partner.
# Varying the shift (1, 2, 1) across the three blocks spreads pairings
# across more than one pair of domains instead of always matching the same
# two (a fixed shift=1 for all three blocks would only ever pair N<->E,
# E<->O, O<->A, A<->C, C<->N — never e.g. N<->O).
_BIGFIVE_BLOCKS = [(1, 2, 1), (3, 4, 2), (5, 6, 1)]

# (domain, facet) of the "lo" side -> scenario intro
BIGFIVE_FRAMES: dict[tuple[str, int], str] = {
    ("E", 1): "В новом классе тебе нужно освоиться. Что бы ты сделал в первую очередь?",
    ("E", 3): "Друзья затеяли шумную игру во дворе. Что тебе ближе?",
    ("E", 5): "На выходных вы всей семьёй решаете, куда пойти. Что тебе ближе?",
    ("C", 5): "Вы собираетесь в поход, а погода вдруг испортилась. Что тебе ближе?",
}

# Manual overrides: the shift-based match for (O,facet1)/(A,facet2) paired
# "У меня богатая фантазия" against "Использую других для своей выгоды" —
# two orthogonal, tonally mismatched items. Changing the block's shift would
# only relocate the same awkward item (A2) onto a different partner, not
# remove it, so instead we locally swap O1's and C1's targets within this
# one block (both stay within facet_hi=2, so every item is still used
# exactly once — verified by the coverage assert below).
_BIGFIVE_OVERRIDES: dict[tuple[str, int], str] = {
    ("O", 1): "N",
    ("C", 1): "A",
}

_bigfive_used_keys: set[tuple[str, int]] = set()

for _facet_lo, _facet_hi, _shift in _BIGFIVE_BLOCKS:
    for _d_idx, _domain_lo in enumerate(_DOMAINS):
        _override_domain = _BIGFIVE_OVERRIDES.get((_domain_lo, _facet_lo))
        _domain_hi = _override_domain or _DOMAINS[(_d_idx + _shift) % 5]
        assert _domain_lo != _domain_hi
        _left = _bigfive_by_domain_facet[(_domain_lo, _facet_lo)]
        _right = _bigfive_by_domain_facet[(_domain_hi, _facet_hi)]
        _bigfive_used_keys.add((_domain_lo, _facet_lo))
        _bigfive_used_keys.add((_domain_hi, _facet_hi))
        _pair_index += 1
        PAIRS.append({
            "instrument": "big_five",
            "pair_index": _pair_index,
            "question_a_order": _left["order"],
            "question_b_order": _right["order"],
            "frame": BIGFIVE_FRAMES.get((_domain_lo, _facet_lo)),
        })

assert _pair_index == 34, f"expected 19+15=34 total pairs, got {_pair_index}"
assert _bigfive_used_keys == set(_bigfive_by_domain_facet.keys()), (
    "not every junior Big Five item was used exactly once"
)

_frame_count = sum(1 for p in PAIRS if p["frame"])
assert 8 <= _frame_count <= 10, f"expected 8-10 framed pairs for variety, got {_frame_count}"
