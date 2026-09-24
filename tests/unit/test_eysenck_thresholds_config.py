"""PRO-338 Ф1.5: Eysenck cut-offs come from the versioned JSON file, not
code — changing them must not need a code change. Mirrors
test_validity_thresholds_config.py's pattern (PRO-297)."""
import json

import pytest

from app.config import (
    EysenckThresholds,
    eysenck_thresholds,
    load_eysenck_thresholds,
)


def test_thresholds_load_from_the_shipped_file() -> None:
    assert isinstance(eysenck_thresholds, EysenckThresholds)
    assert isinstance(eysenck_thresholds.version, int)
    assert len(eysenck_thresholds.extraversion_bounds) == 4
    assert len(eysenck_thresholds.neuroticism_bounds) == 3
    assert eysenck_thresholds.lie_scale_max_ok == 4


def test_shipped_file_is_valid_json_with_a_version() -> None:
    from app.config import _EYSENCK_THRESHOLDS_PATH

    raw = json.loads(_EYSENCK_THRESHOLDS_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw["version"], int)
    assert raw["extraversion_bounds"] == list(eysenck_thresholds.extraversion_bounds)


def test_lie_scale_flagged_boundary_is_strictly_greater_than_4() -> None:
    t = EysenckThresholds(
        version=1, lie_scale_max_ok=4,
        extraversion_bounds=(4, 8, 14, 19), neuroticism_bounds=(8, 13, 19),
    )
    assert t.lie_scale_flagged(0) is False
    assert t.lie_scale_flagged(4) is False  # inclusive "ok" boundary
    assert t.lie_scale_flagged(5) is True
    assert t.lie_scale_flagged(9) is True


def test_extraversion_level_buckets_against_the_source_spec() -> None:
    t = EysenckThresholds(
        version=1, lie_scale_max_ok=4,
        extraversion_bounds=(4, 8, 14, 19), neuroticism_bounds=(8, 13, 19),
    )
    assert t.extraversion_level(0) == "deep_introvert"
    assert t.extraversion_level(4) == "deep_introvert"  # <5
    assert t.extraversion_level(5) == "introvert"
    assert t.extraversion_level(8) == "introvert"  # 5-8
    assert t.extraversion_level(9) == "ambivert"
    assert t.extraversion_level(14) == "ambivert"  # 9-14
    assert t.extraversion_level(15) == "extravert"
    assert t.extraversion_level(19) == "extravert"  # 15-19
    assert t.extraversion_level(20) == "bright_extravert"  # >19


def test_neuroticism_level_buckets_against_the_source_spec() -> None:
    t = EysenckThresholds(
        version=1, lie_scale_max_ok=4,
        extraversion_bounds=(4, 8, 14, 19), neuroticism_bounds=(8, 13, 19),
    )
    assert t.neuroticism_level(0) == "low"
    assert t.neuroticism_level(8) == "low"  # <9
    assert t.neuroticism_level(9) == "medium"
    assert t.neuroticism_level(13) == "medium"  # 9-13
    assert t.neuroticism_level(14) == "high"
    assert t.neuroticism_level(19) == "high"  # 14-19
    assert t.neuroticism_level(20) == "very_high"  # >19


def test_new_threshold_keys_need_no_code_change(tmp_path) -> None:
    p = tmp_path / "v.json"
    p.write_text(
        json.dumps({
            "version": 2,
            "lie_scale_max_ok": 4,
            "extraversion_bounds": [4, 8, 14, 19],
            "neuroticism_bounds": [8, 13, 19],
            "future_key": "x",
        }),
        encoding="utf-8",
    )
    t = load_eysenck_thresholds(p)
    assert t.version == 2
    assert t.model_extra["future_key"] == "x"


def test_thresholds_are_frozen() -> None:
    with pytest.raises(Exception):
        eysenck_thresholds.version = 999
