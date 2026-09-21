"""PRO-338 Ф3.5: АСТУР СПН-group thresholds come from a versioned JSON
file, not code. Mirrors test_belbin_thresholds_config.py's pattern."""
import json

import pytest

from app.config import AsturThresholds, astur_thresholds, load_astur_thresholds


def test_thresholds_load_from_the_shipped_file() -> None:
    assert isinstance(astur_thresholds, AsturThresholds)
    assert isinstance(astur_thresholds.version, int)
    assert astur_thresholds.spn_bounds == (11, 32, 64, 95)


def test_shipped_file_is_valid_json_with_a_version() -> None:
    from app.config import _ASTUR_THRESHOLDS_PATH

    raw = json.loads(_ASTUR_THRESHOLDS_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw["version"], int)
    assert raw["spn_bounds"] == list(astur_thresholds.spn_bounds)


def test_spn_group_buckets_against_the_configured_bounds() -> None:
    t = AsturThresholds(version=1, spn_bounds=(12, 37, 88, 113))
    assert t.spn_group(0) == 5
    assert t.spn_group(12) == 5
    assert t.spn_group(13) == 4
    assert t.spn_group(37) == 4
    assert t.spn_group(38) == 3
    assert t.spn_group(88) == 3
    assert t.spn_group(89) == 2
    assert t.spn_group(113) == 2
    assert t.spn_group(114) == 1
    assert t.spn_group(127) == 1


def test_new_threshold_keys_need_no_code_change(tmp_path) -> None:
    p = tmp_path / "v.json"
    p.write_text(
        json.dumps({"version": 2, "spn_bounds": [12, 37, 88, 113], "future_key": "x"}),
        encoding="utf-8",
    )
    t = load_astur_thresholds(p)
    assert t.version == 2
    assert t.model_extra["future_key"] == "x"


def test_thresholds_are_frozen() -> None:
    with pytest.raises(Exception):
        astur_thresholds.version = 999
