"""Deterministic placement of protocol-validity items inside the Likert
battery (epic PRO-282, phase 1; PRO-298).

The 20 MC-SDS + N infrequency questions are placed **inside the RIASEC
block**, wire-tagged `instrument='riasec'` to match their neighbours (see
question_service._VALIDITY_WIRE_INSTRUMENT), so they are not set apart by
section or position. They keep rendering on Big Five's agree/disagree scale
(`QuestionResponse.bigfive_scale`, decided independently of `instrument`)
because the item texts are agree/disagree statements ("Я всегда…", "Я
никогда…"), not RIASEC's "Мне нравится…" liking statements — see
question_service._bigfive_scale. Two constraints from how the client renders
the battery:

- the client re-sorts questions by `order` (buildDisplaySequence.ts), so the
  interleave has to live in the `order` numbers the API returns, not just in
  list position — `question_service.get_all_questions` renumbers the whole
  returned sequence densely after calling this;
- the client picks the Likert scale by `bigfive_scale`, not by `instrument`,
  so validity items are placed **within the RIASEC block** while still
  getting the accuracy scale.

`interleave_validity` is pure and deterministic on `seed` (the assessment id):
the same student always gets the same battery, but the positions are not a
fixed "every Nth" pattern and differ between students.
"""
import random

from app.models.question import Question

# Keep validity items clear of the first / last few RIASEC items. RIASEC is
# the very first instrument block in the battery (question_service seeds it
# at the lowest `order` range), so this margin IS the global "not in the
# first/last 10 positions of the presented battery" rule (psych-block-spec.md
# §A8.2) on the head side — there is no preceding block to add extra offset,
# unlike when validity items were spliced into Big Five (which always had the
# RIASEC block ahead of it). Must stay >= 10.
_EDGE_MARGIN = 10
# At least this many RIASEC items between any two validity items — no runs.
_MIN_BASE_BETWEEN = 2


def interleave_validity(
    base_run: list[Question],
    validity_items: list[Question],
    *,
    seed: int,
    edge_margin: int = _EDGE_MARGIN,
    min_base_between: int = _MIN_BASE_BETWEEN,
) -> list[Question]:
    """Return `base_run` (the contiguous RIASEC block) with `validity_items`
    spread through it deterministically. No item is dropped; on a run too
    short for the spacing rule the constraints relax gracefully rather than
    raising."""
    if not validity_items:
        return list(base_run)

    n_base = len(base_run)
    n_val = len(validity_items)
    rng = random.Random(seed)

    lo = min(edge_margin, max(0, n_base // 4))
    hi = max(lo + 1, n_base - edge_margin)  # slot i means "insert before base_run[i]"
    window = hi - lo

    gap = min_base_between
    while gap > 1 and (n_val - 1) * gap + 1 > window:
        gap -= 1

    if n_val <= window:
        slots = sorted(rng.sample(range(lo, hi), n_val))
    else:  # more validity items than usable slots — even round-robin fallback
        slots = [lo + (i * window) // n_val for i in range(n_val)]

    # Enforce the minimum spacing without losing items, then pull the whole
    # set back inside the run if spacing pushed the tail past the end.
    for i in range(1, len(slots)):
        if slots[i] - slots[i - 1] < gap:
            slots[i] = slots[i - 1] + gap
    overflow = slots[-1] - (n_base - 1)
    if overflow > 0:
        slots = [max(0, s - overflow) for s in slots]

    # Which validity item lands where is shuffled too, so sd_key / infrequency
    # rows are not a predictable fixed sub-order inside the battery.
    picks = list(validity_items)
    rng.shuffle(picks)

    by_slot: dict[int, Question] = {}
    for slot, question in zip(slots, picks):
        while slot in by_slot:  # de-dupe after an overflow pull-back
            slot += 1
        by_slot[slot] = question

    out: list[Question] = []
    for idx, question in enumerate(base_run):
        if idx in by_slot:
            out.append(by_slot.pop(idx))
        out.append(question)
    for slot in sorted(by_slot):  # any slot >= n_base (degenerate runs only)
        out.append(by_slot[slot])
    return out
