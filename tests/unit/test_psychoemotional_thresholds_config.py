"""PRO-305: psychoemotional thresholds load from the versioned JSON file,
not code; `version` is readable so the engine (PRO-309) can stamp it onto
`psychoemotional_runs.thresholds_version`."""
import json

import pytest

from app.config import (
    PsychoEmotionalThresholds,
    load_psychoemotional_thresholds,
    psychoemotional_thresholds,
)


def test_thresholds_load_from_the_shipped_file() -> None:
    t = psychoemotional_thresholds
    assert isinstance(t, PsychoEmotionalThresholds)
    assert isinstance(t.version, int)
    assert set(t.so) >= {"norm_max", "elevated_max"}
    assert set(t.anxiety) >= {"low_max", "moderate_max"}
    assert set(t.compensation) >= {"norm_max", "moderate_max"}
    assert set(t.vk) >= {"exhaustion_max", "norm_max"}
    assert set(t.validity) >= {
        "circle_fast_sec",
        "total_fast_sec",
        "split_pairs_unstable",
        "d_unstable",
        "pause_min_sec",
    }


def test_shipped_file_is_valid_json_with_a_version() -> None:
    from app.config import _PSYCHOEMOTIONAL_THRESHOLDS_PATH

    raw = json.loads(_PSYCHOEMOTIONAL_THRESHOLDS_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw["version"], int)
    assert raw["so"] == psychoemotional_thresholds.so


def test_bands_are_ordered() -> None:
    t = psychoemotional_thresholds
    assert t.so["norm_max"] < t.so["elevated_max"]
    assert t.anxiety["low_max"] < t.anxiety["moderate_max"]
    assert t.compensation["norm_max"] < t.compensation["moderate_max"]
    assert t.vk["exhaustion_max"] < t.vk["norm_max"]


def test_new_keys_need_no_code_change(tmp_path) -> None:
    p = tmp_path / "v.json"
    p.write_text(
        json.dumps(
            {
                "version": 2,
                "so": {"norm_max": 15, "elevated_max": 23},
                "anxiety": {"low_max": 3, "moderate_max": 6},
                "compensation": {"norm_max": 1, "moderate_max": 4},
                "vk": {"exhaustion_max": 0.9, "norm_max": 1.8},
                "validity": {
                    "circle_fast_sec": 10,
                    "total_fast_sec": 20,
                    "split_pairs_unstable": 3,
                    "d_unstable": 20,
                    "pause_min_sec": 120,
                },
                "age_adjust": {"anxiety_shift": 1},  # future key, no model field
            }
        ),
        encoding="utf-8",
    )
    t = load_psychoemotional_thresholds(p)
    assert t.version == 2
    assert t.model_extra["age_adjust"] == {"anxiety_shift": 1}


def test_thresholds_are_frozen() -> None:
    with pytest.raises(Exception):
        psychoemotional_thresholds.version = 999
