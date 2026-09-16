"""PRO-338 Ф1.11: Boyko empathy cut-offs come from the versioned JSON file,
not code. Mirrors test_elers_thresholds_config.py's pattern."""
import json

import pytest

from app.config import (
    BoykoEmpathyThresholds,
    boyko_empathy_thresholds,
    load_boyko_empathy_thresholds,
)


def test_thresholds_load_from_the_shipped_file() -> None:
    assert isinstance(boyko_empathy_thresholds, BoykoEmpathyThresholds)
    assert isinstance(boyko_empathy_thresholds.version, int)
    assert len(boyko_empathy_thresholds.bounds) == 3


def test_shipped_file_is_valid_json_with_a_version() -> None:
    from app.config import _BOYKO_EMPATHY_THRESHOLDS_PATH

    raw = json.loads(_BOYKO_EMPATHY_THRESHOLDS_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw["version"], int)
    assert raw["bounds"] == list(boyko_empathy_thresholds.bounds)


def test_level_buckets_against_the_source_spec_including_the_boundary_score() -> None:
    t = BoykoEmpathyThresholds(version=1, bounds=(14, 21, 29))
    assert t.level(0) == "very_low"
    assert t.level(14) == "very_low"  # the resolved ambiguous boundary
    assert t.level(15) == "underestimated"
    assert t.level(21) == "underestimated"
    assert t.level(22) == "average"
    assert t.level(29) == "average"
    assert t.level(30) == "very_high"
    assert t.level(36) == "very_high"  # theoretical max


def test_new_threshold_keys_need_no_code_change(tmp_path) -> None:
    p = tmp_path / "v.json"
    p.write_text(json.dumps({"version": 2, "bounds": [14, 21, 29], "future_key": "x"}), encoding="utf-8")
    t = load_boyko_empathy_thresholds(p)
    assert t.version == 2
    assert t.model_extra["future_key"] == "x"


def test_thresholds_are_frozen() -> None:
    with pytest.raises(Exception):
        boyko_empathy_thresholds.version = 999
