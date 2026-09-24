"""АСТУР per-subtest submit contract (PRO-338 Ф3.4). One request per
subtest (1-7), not one big payload like Belbin/psychoemotional — a long,
multi-subtest test must not lose progress on a dropped connection."""
import uuid
from typing import Any

from pydantic import BaseModel, Field


class StartAsturSubtestResponse(BaseModel):
    run_id: uuid.UUID
    subtest: str  # scripts/astur_bank.py's SUBTESTS[i]["key"]
    started_at: str  # ISO 8601, server clock — the timer engine's anchor


class SubmitAsturSubtestRequest(BaseModel):
    # item index (1-based, as string, matching the content bank's own
    # 1..item_count numbering) -> answer. Shape of the VALUE varies by
    # subtest (a chosen option string, 2 words, open text, an ordered
    # concept list, 2 numbers...) — validated structurally (right key set)
    # by the service, interpreted for correctness only by Ф3.5's scoring,
    # not here.
    answers: dict[str, Any]
    # Lability (subtest 3) ONLY: per-item client-reported elapsed time —
    # see app/services/subtest_timer.py's docstring for why this one
    # subtest is client-timed instead of server-timed. Required when
    # subtest == 3, rejected (must be absent) otherwise.
    elapsed_ms: dict[str, int] | None = None

    model_config = {"extra": "forbid"}


class SubmitAsturSubtestResponse(BaseModel):
    run_id: uuid.UUID
    subtest: str
    # None if the client never called .../start for this subtest — the
    # answer is still accepted (Ф3.4: never lose progress over a missing
    # timer), just without a server-verified duration.
    actual_ms: int | None
    # Lability only: item indices whose reported elapsed_ms exceeded the
    # configured per-item limit (app/data/astur_timer_config.json).
    over_limit_items: list[str] = Field(default_factory=list)


class AsturContentSubtest(BaseModel):
    """One subtest's renderable content — item shape varies by `key`
    (`scripts/astur_bank.py`'s own per-subtest item schema), so `items`
    stays loosely typed here the same way `SubmitAsturSubtestRequest.
    answers` does; the frontend switches on `key` to interpret it. Never
    carries a correct-answer field (`answer`/`score_2`/`dynamic`/...) —
    same non-disclosure principle as every other scored instrument in this
    epic. `logical_schemas`' `concepts` list is shuffled per request (it's
    the correct order in the content bank — sending it as-is would hand
    the respondent the answer)."""

    number: int
    key: str
    name: str
    instruction: str
    item_count: int
    scored: bool
    # None only for `lability` — it uses `lability_item_limit_ms` (below)
    # per command instead of one whole-subtest budget.
    time_limit_sec: int | None
    items: list[dict[str, Any]]


class AsturContentResponse(BaseModel):
    subtests: list[AsturContentSubtest]
    lability_item_limit_ms: int
