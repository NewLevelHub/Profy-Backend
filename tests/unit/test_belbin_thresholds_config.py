"""PRO-338 Ф2.5: Belbin's avoidance-zone cut-off comes from the versioned
JSON file, not code. Mirrors test_eysenck_thresholds_config.py's pattern."""
import json

import pytest

from app.config import BelbinThresholds, belbin_thresholds, load_belbin_thresholds


def test_thresholds_load_from_the_shipped_file() -> None:
    assert isinstance(belbin_thresholds, BelbinThresholds)
    assert isinstance(belbin_thresholds.version, int)
    assert belbin_thresholds.avoidance_max_score == 3


def test_shipped_file_is_valid_json_with_a_version() -> None:
    from app.config import _BELBIN_THRESHOLDS_PATH

    raw = json.loads(_BELBIN_THRESHOLDS_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw["version"], int)
    assert raw["avoidance_max_score"] == belbin_thresholds.avoidance_max_score


def test_is_avoidance_zone_boundary_is_inclusive_at_3() -> None:
    t = BelbinThresholds(version=1, avoidance_max_score=3)
    assert t.is_avoidance_zone(0) is True
    assert t.is_avoidance_zone(3) is True
    assert t.is_avoidance_zone(4) is False
    assert t.is_avoidance_zone(10) is False


def test_new_threshold_keys_need_no_code_change(tmp_path) -> None:
    p = tmp_path / "v.json"
    p.write_text(
        json.dumps({"version": 2, "avoidance_max_score": 3, "future_key": "x"}),
        encoding="utf-8",
    )
    t = load_belbin_thresholds(p)
    assert t.version == 2
    assert t.model_extra["future_key"] == "x"


def test_thresholds_are_frozen() -> None:
    with pytest.raises(Exception):
        belbin_thresholds.version = 999
