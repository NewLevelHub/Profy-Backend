"""Timing for АСТУР attempts (PRO-338 Ф3.4, extended in PRO-427).

- Per-subtest: the server is the source of truth. `/start` records a server
  `started_at` on the persisted run; submit computes elapsed from it. A
  missing start is not an error (a late/retried client must never lose
  answers), it just leaves the subtest without verified timing — scoring
  flags that in protocol quality.
- Quick instructions: each command has a few-second budget, so a network
  round-trip per command is not viable; the client reports per-command
  elapsed ms, the server flags commands over the version's limit and derives
  each command's answer timestamp from its own receive time.
"""
from datetime import datetime, timedelta, timezone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def start_subtest(subtest_started_at: dict, subtest_key: str, *, now: datetime | None = None) -> None:
    """Record the first server start and keep it on retries/reloads.

    `/start` is idempotent: resetting this timestamp would let a respondent
    obtain a fresh time limit by reloading the page.
    """
    if subtest_key not in subtest_started_at:
        subtest_started_at[subtest_key] = (now or now_utc()).isoformat()


def elapsed_ms_since_start(subtest_started_at: dict, subtest_key: str, *, now: datetime | None = None) -> int | None:
    raw = subtest_started_at.get(subtest_key)
    if raw is None:
        return None
    elapsed = (now or now_utc()) - datetime.fromisoformat(raw)
    return max(0, int(elapsed.total_seconds() * 1000))


def quick_answer_timestamps(elapsed_ms: dict[str, int], *, received_at: datetime) -> dict[str, datetime]:
    """Answer time of each command, counted back from when the server
    received the batch: the last command was answered at ~receive time, and
    each earlier one before the time spent on every command after it."""
    stamps: dict[str, datetime] = {}
    remaining = timedelta()
    for key in sorted(elapsed_ms, key=int, reverse=True):
        stamps[key] = received_at - remaining
        remaining += timedelta(milliseconds=max(0, elapsed_ms[key]))
    return stamps


def item_over_limit(elapsed_ms: int, limit_ms: int) -> bool:
    return elapsed_ms > limit_ms
