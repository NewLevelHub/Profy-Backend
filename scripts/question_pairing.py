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
no new statement content, no new response table (a pick is written as two
ordinary UserResponse rows, see app/services/question_pair_service.py).

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

Every pair may optionally carry a `frame` — a short scenario line shown
above the pair, so not every screen looks identical.
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


def _riasec_pairs(
    items: list[dict], frames: dict[tuple[str, int], str], age_tier: str, start_index: int,
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
            pairs.append({
                "instrument": "riasec",
                "age_tier": age_tier,
                "pair_index": idx,
                "question_a_order": left["order"],
                "question_b_order": right["order"],
                "frame": frames.get((left_type, pos)),
            })

    assert used == {q["order"] for q in items}, (
        f"[{age_tier}] not every RIASEC item was used exactly once"
    )
    return pairs, idx


def _bigfive_pairs(
    items: list[dict],
    overrides: dict[tuple[str, int], str],
    frames: dict[tuple[str, int], str],
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
            pairs.append({
                "instrument": "big_five",
                "age_tier": age_tier,
                "pair_index": idx,
                "question_a_order": left["order"],
                "question_b_order": right["order"],
                "frame": frames.get((domain_lo, facet_lo)),
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

# (type, 1-based position within that type's junior items) -> scenario intro
_JUNIOR_RIASEC_FRAMES: dict[tuple[str, int], str] = {
    ("R", 3): "Представь: во дворе твой друг с кем-то поссорился, а ещё у тебя сломался велосипед. Что бы ты сделал в первую очередь?",
    ("I", 1): "Ты оказался в незнакомом месте. Что бы ты сделал?",
    ("I", 5): "На каникулах можно заняться чем угодно. Что тебе ближе?",
    ("A", 3): "В игре нужно быстро решить головоломку. Что тебе ближе?",
    ("A", 7): "На школьном празднике все готовят выступление. Что тебе ближе?",
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

_JUNIOR_BIGFIVE_FRAMES: dict[tuple[str, int], str] = {
    ("E", 1): "В новом классе тебе нужно освоиться. Что бы ты сделал в первую очередь?",
    ("E", 3): "Друзья затеяли шумную игру во дворе. Что тебе ближе?",
    ("E", 5): "На выходных вы всей семьёй решаете, куда пойти. Что тебе ближе?",
    ("C", 5): "Вы собираетесь в поход, а погода вдруг испортилась. Что тебе ближе?",
}

_junior_riasec_pairs, _idx = _riasec_pairs(_riasec_junior, _JUNIOR_RIASEC_FRAMES, "junior", 0)
_junior_bigfive_pairs, _idx = _bigfive_pairs(
    _bigfive_junior, _JUNIOR_BIGFIVE_OVERRIDES, _JUNIOR_BIGFIVE_FRAMES, "junior", _idx
)

assert len(_junior_riasec_pairs) == 19, f"expected 19 junior RIASEC pairs, got {len(_junior_riasec_pairs)}"
assert len(_junior_bigfive_pairs) == 15, f"expected 15 junior Big Five pairs, got {len(_junior_bigfive_pairs)}"
assert _idx == 34, f"expected 34 junior pairs total, got {_idx}"

# ══════════════════ Middle (subset woven into the Likert flow) ══════════════

_riasec_middle = [q for q in _RIASEC_QUESTIONS if q["age_tier"] == "middle"]
_bigfive_middle = [q for q in _BIGFIVE_QUESTIONS if q["age_tier"] == "middle"]

assert len(_riasec_middle) == 36, f"expected 36 middle-only RIASEC items, got {len(_riasec_middle)}"
assert len(_bigfive_middle) == 30, f"expected 30 middle-only Big Five items, got {len(_bigfive_middle)}"

# (type, 1-based position within that type's middle-only items) -> scenario intro
_MIDDLE_RIASEC_FRAMES: dict[tuple[str, int], str] = {
    ("R", 3): "Класс готовит проект к концу четверти, и тебе нужно решить, как в нём участвовать. Что тебе ближе?",
    ("I", 3): "На школьном мероприятии нужно и подготовить доклад, и выступить перед всеми. Что тебе ближе?",
    ("I", 5): "У тебя выдался свободный вечер. Что тебе ближе?",
    ("A", 3): "Тебе поручили организовать классную вечеринку. Что тебе ближе?",
    ("A", 5): "На уроке предложили придумать нестандартный проект. Что тебе ближе?",
}

# Same awkward-shift-pairing issue as junior's block, same fix: locally swap
# two targets within the facet3/4 block instead of relocating the mismatch.
# Original shift(2) pairs (E,3)->(A,4) "Стараюсь быть лидером" vs "Кричу на
# людей" — tonally mismatched (achievement vs aggression). Swapping E3's and
# O3's targets gives (E,3)->(C,4) "делаю больше, чем ожидают" (coherent,
# achievement-themed) and (O,3)->(A,4) "сопереживаю" vs "кричу на людей"
# (a meaningful warmth-vs-aggression contrast, not a random mismatch).
_MIDDLE_BIGFIVE_OVERRIDES: dict[tuple[str, int], str] = {
    ("O", 1): "N",
    ("C", 1): "A",
    ("E", 3): "C",
    ("O", 3): "A",
}

_MIDDLE_BIGFIVE_FRAMES: dict[tuple[str, int], str] = {
    ("E", 1): "Ты переходишь в новую школу. Что тебе ближе в первую неделю?",
    ("E", 3): "Учитель поручил группе важное задание. Что тебе ближе?",
    ("C", 5): "Планы на выходные внезапно поменялись. Что тебе ближе?",
}

_middle_riasec_pairs, _idx = _riasec_pairs(_riasec_middle, _MIDDLE_RIASEC_FRAMES, "middle", _idx)
_middle_bigfive_pairs, _idx = _bigfive_pairs(
    _bigfive_middle, _MIDDLE_BIGFIVE_OVERRIDES, _MIDDLE_BIGFIVE_FRAMES, "middle", _idx
)

assert len(_middle_riasec_pairs) == 18, f"expected 18 middle RIASEC pairs, got {len(_middle_riasec_pairs)}"
assert len(_middle_bigfive_pairs) == 15, f"expected 15 middle Big Five pairs, got {len(_middle_bigfive_pairs)}"
assert _idx == 67, f"expected 34+33=67 pairs total, got {_idx}"

PAIRS: list[dict] = [
    *_junior_riasec_pairs, *_junior_bigfive_pairs,
    *_middle_riasec_pairs, *_middle_bigfive_pairs,
]

_junior_frame_count = sum(1 for p in _junior_riasec_pairs + _junior_bigfive_pairs if p["frame"])
assert 8 <= _junior_frame_count <= 10, f"expected 8-10 framed junior pairs, got {_junior_frame_count}"

_middle_frame_count = sum(1 for p in _middle_riasec_pairs + _middle_bigfive_pairs if p["frame"])
assert 6 <= _middle_frame_count <= 10, f"expected ~8 framed middle pairs, got {_middle_frame_count}"
