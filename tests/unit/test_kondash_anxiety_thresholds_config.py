"""PRO-338 Ф1.11: Kondash-derived confidence cut-offs come from the
versioned JSON file, not code. Mirrors test_elers_thresholds_config.py's
pattern."""
import json

import pytest

from app.config import (
    KondashAnxietyThresholds,
    kondash_anxiety_thresholds,
    load_kondash_anxiety_thresholds,
)


def test_thresholds_load_from_the_shipped_file() -> None:
    assert isinstance(kondash_anxiety_thresholds, KondashAnxietyThresholds)
    assert isinstance(kondash_anxiety_thresholds.version, int)
    assert len(kondash_anxiety_thresholds.interpersonal_sten10_by_age) == 4
    assert kondash_anxiety_thresholds.confidence_sten_bounds == (3, 6)


def test_shipped_file_is_valid_json_with_a_version() -> None:
    from app.config import _KONDASH_ANXIETY_THRESHOLDS_PATH

    raw = json.loads(_KONDASH_ANXIETY_THRESHOLDS_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw["version"], int)
    assert raw["confidence_sten_bounds"] == list(kondash_anxiety_thresholds.confidence_sten_bounds)


def test_interpersonal_sten10_picks_the_right_age_bracket() -> None:
    t = kondash_anxiety_thresholds
    assert t.interpersonal_sten10(10) == 24
    assert t.interpersonal_sten10(11) == 24
    assert t.interpersonal_sten10(12) == 21
    assert t.interpersonal_sten10(13) == 28
    assert t.interpersonal_sten10(14) == 28
    assert t.interpersonal_sten10(15) == 18
    assert t.interpersonal_sten10(16) == 18


def test_interpersonal_sten10_falls_back_to_the_last_bracket_above_16() -> None:
    t = kondash_anxiety_thresholds
    assert t.interpersonal_sten10(17) == 18
    assert t.interpersonal_sten10(25) == 18


def test_confidence_level_buckets_against_the_ticket_text() -> None:
    t = kondash_anxiety_thresholds
    assert t.confidence_level(1) == "high"
    assert t.confidence_level(3) == "high"
    assert t.confidence_level(4) == "normative"
    assert t.confidence_level(6) == "normative"
    assert t.confidence_level(7) == "low"
    assert t.confidence_level(10) == "low"


def test_new_threshold_keys_need_no_code_change(tmp_path) -> None:
    p = tmp_path / "v.json"
    p.write_text(json.dumps({
        "version": 2,
        "interpersonal_sten10_by_age": [{"max_age": 16, "sten10": 18}],
        "confidence_sten_bounds": [3, 6],
        "future_key": "x",
    }), encoding="utf-8")
    t = load_kondash_anxiety_thresholds(p)
    assert t.version == 2
    assert t.model_extra["future_key"] == "x"


def test_thresholds_are_frozen() -> None:
    with pytest.raises(Exception):
        kondash_anxiety_thresholds.version = 999
