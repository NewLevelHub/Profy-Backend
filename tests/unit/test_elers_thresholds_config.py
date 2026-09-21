"""PRO-338 Ф1.8: Elers cut-offs come from the versioned JSON file, not
code — changing them must not need a code change. Mirrors
test_eysenck_thresholds_config.py's pattern."""
import json

import pytest

from app.config import (
    ElersThresholds,
    elers_thresholds,
    load_elers_thresholds,
)


def test_thresholds_load_from_the_shipped_file() -> None:
    assert isinstance(elers_thresholds, ElersThresholds)
    assert isinstance(elers_thresholds.version, int)
    assert len(elers_thresholds.bounds) == 3


def test_shipped_file_is_valid_json_with_a_version() -> None:
    from app.config import _ELERS_THRESHOLDS_PATH

    raw = json.loads(_ELERS_THRESHOLDS_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw["version"], int)
    assert raw["bounds"] == list(elers_thresholds.bounds)


def test_level_buckets_against_the_source_spec() -> None:
    t = ElersThresholds(version=1, bounds=(10, 16, 20))
    assert t.level(1) == "low"
    assert t.level(10) == "low"  # 1-10
    assert t.level(11) == "medium"
    assert t.level(16) == "medium"  # 11-16
    assert t.level(17) == "moderately_high"
    assert t.level(20) == "moderately_high"  # 17-20
    assert t.level(21) == "too_high"  # >20
    assert t.level(32) == "too_high"  # theoretical max (23 yes + 9 no keyed items)


def test_new_threshold_keys_need_no_code_change(tmp_path) -> None:
    p = tmp_path / "v.json"
    p.write_text(json.dumps({"version": 2, "bounds": [10, 16, 20], "future_key": "x"}), encoding="utf-8")
    t = load_elers_thresholds(p)
    assert t.version == 2
    assert t.model_extra["future_key"] == "x"


def test_thresholds_are_frozen() -> None:
    with pytest.raises(Exception):
        elers_thresholds.version = 999
