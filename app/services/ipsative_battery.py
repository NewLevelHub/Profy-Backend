"""PRO-338 Ф0.6 — generic ipsative point-allocation engine.

Built once, for Belbin (Фаза 2, `belbin_runs` table — see
03-Фаза2-Белбин.md Ф2.3), but deliberately not tied to that test: any
instrument shaped as "N blocks, each block a fixed set of M items, the
respondent splits a fixed point total across that block's items" reuses
this module. Belbin itself is 7 blocks x 8 items, 10 points per block
(Σ=70) — those numbers are the *caller's* content, never hardcoded here.

This is a pure service/validation layer, not a DB entity: raw allocations
are stored as JSONB (`{item_id: points}` per block) directly in whichever
table the concrete test owns (Belbin -> `belbin_runs`), per the Ф0.2
decision to not invent a shared ipsative-battery table.

Two responsibilities, matching the ticket exactly:
  - `validate_allocation()` — one block's raw `{item_id: points}` input is
    untrustworthy client data until this passes. The frontend's own
    live-remaining-points UI (Ф0.7, PointAllocator.tsx) is a UX nicety, not
    a source of truth — every allocation is re-validated here regardless of
    what the client claims.
  - `aggregate_by_key()` — once a whole battery's allocations are validated
    and stored, sums raw item-level points into the test's actual scoring
    keys (e.g. Belbin's 8 role letters) across every block.
"""
from collections.abc import Collection, Mapping, Sequence
from typing import TypeAlias

from fastapi import HTTPException, status

# One block's raw input: item_id -> points assigned to that item. Values are
# validated (>=0, block sums to the block's total) by validate_allocation()
# before they're trusted anywhere else.
PointAllocation: TypeAlias = Mapping[str, int]


def validate_allocation(
    allocation: PointAllocation,
    *,
    expected_items: Collection[str],
    total: int,
) -> None:
    """Raises HTTPException(422) if `allocation` is not a valid split of
    exactly `total` points across exactly `expected_items` — never trusts
    that the client already enforced this (TZ per Ф0.6: the frontend
    live-remaining-points indicator is a UX hint, not validation).

    Checked, in order (each violation gets its own message so a 422 tells
    the client exactly what to fix, not just "invalid"):
      1. the allocation's keys are exactly `expected_items` — catches both
         missing items and unknown/stray item_ids in one comparison (also
         covers "wrong item count" implicitly: a set of the right items is
         necessarily the right count).
      2. every value is a non-negative integer.
      3. the values sum to exactly `total` — not "at most", ipsative scoring
         requires the full budget spent every time.

    Returns None (a guard, not a transform) — call it, then use the
    already-validated `allocation` as-is."""
    expected = set(expected_items)
    got = set(allocation.keys())
    if got != expected:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "detail": "Allocation does not cover exactly the expected items for this block",
                "missing_items": sorted(expected - got),
                "unexpected_items": sorted(got - expected),
            },
        )

    negative = {item_id: points for item_id, points in allocation.items() if points < 0}
    if negative:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"detail": "Allocation values must be >= 0", "negative_items": negative},
        )

    actual_total = sum(allocation.values())
    if actual_total != total:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "detail": f"Allocation must sum to exactly {total} points, got {actual_total}",
                "expected_total": total,
                "actual_total": actual_total,
            },
        )


def aggregate_by_key(
    allocations: Sequence[PointAllocation],
    item_to_key_map: Mapping[str, str],
) -> dict[str, int]:
    """Sums raw item-level points into scoring keys (e.g. Belbin's 8 role
    letters) across every block of an already-validated battery.

    `allocations` is one `{item_id: points}` dict per block (the same shape
    `validate_allocation` checks, called once per block before this runs —
    this function does not re-validate). `item_to_key_map` maps every
    item_id appearing anywhere in `allocations` to the key it counts
    toward; a battery's content bank owns this map (e.g. Belbin's own
    "point -> role" table), not this generic module.

    An item_id present in `allocations` but missing from `item_to_key_map`
    is a content-authoring bug, not a user-input error — this raises
    `KeyError` (loud and immediate) rather than silently dropping those
    points, which would corrupt every score derived from this battery."""
    totals: dict[str, int] = {}
    for block in allocations:
        for item_id, points in block.items():
            key = item_to_key_map[item_id]
            totals[key] = totals.get(key, 0) + points
    return totals
