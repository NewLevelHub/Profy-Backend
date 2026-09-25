"""PRO-427 — server-side timing for АСТУР attempts."""
from datetime import datetime, timedelta, timezone

from app.services.astur import timing

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)


def test_subtest_elapsed_is_measured_from_the_server_start() -> None:
    started: dict = {}
    timing.start_subtest(started, "awareness", now=NOW)
    assert timing.elapsed_ms_since_start(started, "awareness", now=NOW + timedelta(seconds=90)) == 90_000


def test_missing_start_means_no_verified_timing() -> None:
    assert timing.elapsed_ms_since_start({}, "awareness", now=NOW) is None


def test_quick_answer_timestamps_count_back_from_receive_time() -> None:
    stamps = timing.quick_answer_timestamps({"1": 3000, "2": 2000, "3": 1000}, received_at=NOW)
    assert stamps["3"] == NOW
    assert stamps["2"] == NOW - timedelta(milliseconds=1000)
    assert stamps["1"] == NOW - timedelta(milliseconds=3000)


def test_over_limit_uses_the_versions_limit() -> None:
    assert timing.item_over_limit(20_001, 20_000) is True
    assert timing.item_over_limit(20_000, 20_000) is False
