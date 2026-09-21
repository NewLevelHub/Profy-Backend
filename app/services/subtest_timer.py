"""PRO-338 Ф3.4 — timer engine for АСТУР subtests. Two independent modes,
matching the two different timing needs 04-Фаза3-АСТУР.md calls out:

- **Per-subtest** (subtests 1-2, 4-7 — and lability's own subtest-level
  bookkeeping too, see below): the server is the source of truth for
  elapsed time. `start_subtest()` records a server-side `started_at` the
  moment a subtest begins; `elapsed_ms_since_start()` at submit time
  computes actual elapsed ms from THAT timestamp to `now()` — never from a
  client-reported duration. Survives a dropped connection: `started_at`
  lives on the (already persisted) `AsturRun` row, not in memory.

- **Per-item** (subtest 3, lability): 8 commands, each with its own
  few-second limit. Round-tripping to the server before/after each of 8
  rapid-fire items would inject network latency into a budget measured in
  single-digit seconds — not practical, unlike the whole-subtest case where
  minutes of slack make network latency negligible. So this mode trusts
  the CLIENT's own per-item elapsed_ms (sent alongside every answer in one
  lability submit) and the server's enforcement is a plausibility check —
  `item_over_limit()` flags an item whose reported elapsed exceeds the
  configured limit as a fact stored alongside the answer, never silently
  dropped or rejected; Ф3.5's scoring decides how (or whether) an
  over-limit item affects the accuracy-by-half calculation.
"""
from datetime import datetime, timezone

from app.config import AsturTimerConfig, astur_timer_config


def start_subtest(subtest_started_at: dict, subtest_key: str, *, now: datetime | None = None) -> None:
    """Mutates `subtest_started_at` (an `AsturRun.subtest_started_at` dict)
    in place — caller persists. Re-starting an already-started subtest
    overwrites the earlier timestamp: a client retrying its own `/start`
    call (e.g. after a dropped response) should reset the clock, not stack
    up a stale earlier start time."""
    subtest_started_at[subtest_key] = (now or datetime.now(timezone.utc)).isoformat()


def elapsed_ms_since_start(
    subtest_started_at: dict, subtest_key: str, *, now: datetime | None = None
) -> int | None:
    """`None` if `start_subtest` was never called for this key — a client
    that skips `/start` and submits directly gets no server-verified
    timing (`subtest_timings_ms[key]` stays unset), not a crash; the raw
    answer is still accepted (Ф3.4's "never lose progress" principle beats
    strict timer enforcement)."""
    raw = subtest_started_at.get(subtest_key)
    if raw is None:
        return None
    started_at = datetime.fromisoformat(raw)
    elapsed = (now or datetime.now(timezone.utc)) - started_at
    return max(0, int(elapsed.total_seconds() * 1000))


def item_over_limit(
    elapsed_ms: int, *, config: AsturTimerConfig = astur_timer_config
) -> bool:
    """Per-item (lability) plausibility check — see module docstring for
    why this is client-timed rather than server-timed."""
    return elapsed_ms > config.lability_item_limit_ms
