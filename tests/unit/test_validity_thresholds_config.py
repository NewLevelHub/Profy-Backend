"""PRO-297: protocol-validity thresholds come from the versioned JSON file,
not code — changing them must not need a code change, and the applied
`version` must be readable so validity_service (PRO-299) can stamp it onto
`assessment_validity.thresholds_version`.
"""
import json

import pytest

from app.config import (
    ValidityThresholds,
    load_validity_thresholds,
    validity_thresholds,
)


def test_thresholds_load_from_the_shipped_file() -> None:
    assert isinstance(validity_thresholds, ValidityThresholds)
    assert isinstance(validity_thresholds.version, int)
    assert len(validity_thresholds.sd_bounds) == 2
    assert validity_thresholds.sd_bounds[0] < validity_thresholds.sd_bounds[1]
    for field in ("longstring_max_flag", "irv_low_flag", "infrequency_fail_flag"):
        assert getattr(validity_thresholds, field) is not None


def test_shipped_file_is_valid_json_with_a_version() -> None:
    from app.config import _VALIDITY_THRESHOLDS_PATH

    raw = json.loads(_VALIDITY_THRESHOLDS_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw["version"], int)
    assert raw["sd_bounds"] == list(validity_thresholds.sd_bounds)


def test_sd_level_buckets_against_sd_bounds() -> None:
    # The shipped product bands (PRO-294, adolescent-shifted): 0-8 ok /
    # 9-15 social_desirability / 16-20 high.
    t = ValidityThresholds(
        version=9,
        sd_bounds=(8, 15),
        longstring_max_flag=10,
        irv_low_flag=0.5,
        infrequency_fail_flag=2,
    )
    assert t.sd_level(0) == "ok"
    assert t.sd_level(8) == "ok"  # inclusive lower bound
    assert t.sd_level(9) == "social_desirability"
    assert t.sd_level(15) == "social_desirability"  # inclusive upper bound
    assert t.sd_level(16) == "high"
    assert t.sd_level(20) == "high"


def test_new_threshold_keys_need_no_code_change(tmp_path) -> None:
    """extra keys added to the JSON are readable without touching the model."""
    p = tmp_path / "v.json"
    p.write_text(
        json.dumps(
            {
                "version": 2,
                "sd_bounds": [7, 12],
                "longstring_max_flag": 9,
                "irv_low_flag": 0.4,
                "infrequency_fail_flag": 2,
                "age_correction_points": 2,  # future key, no model field
            }
        ),
        encoding="utf-8",
    )
    t = load_validity_thresholds(p)
    assert t.version == 2
    assert t.model_extra["age_correction_points"] == 2


def test_thresholds_are_frozen() -> None:
    with pytest.raises(Exception):
        validity_thresholds.version = 999
