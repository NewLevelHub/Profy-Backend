"""PRO-338 Ф3.4 — subtest_timer.py: server-side per-subtest timing +
per-item (lability) plausibility checks. Pure functions, no DB."""
from datetime import datetime, timedelta, timezone

from app.config import AsturTimerConfig
from app.services import subtest_timer


def test_start_subtest_writes_an_iso_timestamp() -> None:
    store: dict = {}
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    subtest_timer.start_subtest(store, "awareness", now=now)

    assert store == {"awareness": now.isoformat()}


def test_restarting_overwrites_the_earlier_timestamp() -> None:
    store: dict = {}
    first = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    second = datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc)

    subtest_timer.start_subtest(store, "awareness", now=first)
    subtest_timer.start_subtest(store, "awareness", now=second)

    assert store["awareness"] == second.isoformat()


def test_elapsed_ms_since_start_computes_real_duration() -> None:
    store: dict = {}
    started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    submitted = started + timedelta(seconds=90, milliseconds=500)

    subtest_timer.start_subtest(store, "awareness", now=started)
    elapsed = subtest_timer.elapsed_ms_since_start(store, "awareness", now=submitted)

    assert elapsed == 90500


def test_elapsed_ms_since_start_is_none_when_never_started() -> None:
    assert subtest_timer.elapsed_ms_since_start({}, "awareness") is None


def test_item_over_limit_uses_configured_threshold() -> None:
    config = AsturTimerConfig(version=1, lability_item_limit_ms=5000)

    assert subtest_timer.item_over_limit(4999, config=config) is False
    assert subtest_timer.item_over_limit(5000, config=config) is False  # inclusive boundary
    assert subtest_timer.item_over_limit(5001, config=config) is True
