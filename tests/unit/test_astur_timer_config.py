"""PRO-338 Ф3.4: АСТУР timer config comes from a versioned JSON file, not
code. Mirrors test_belbin_thresholds_config.py's pattern."""
import json

import pytest

from app.config import AsturTimerConfig, astur_timer_config, load_astur_timer_config


def test_config_loads_from_the_shipped_file() -> None:
    assert isinstance(astur_timer_config, AsturTimerConfig)
    assert isinstance(astur_timer_config.version, int)
    assert astur_timer_config.lability_item_limit_ms == 20000


def test_shipped_file_is_valid_json_with_a_version() -> None:
    from app.config import _ASTUR_TIMER_CONFIG_PATH

    raw = json.loads(_ASTUR_TIMER_CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw["version"], int)
    assert raw["lability_item_limit_ms"] == astur_timer_config.lability_item_limit_ms


def test_new_config_keys_need_no_code_change(tmp_path) -> None:
    p = tmp_path / "v.json"
    p.write_text(
        json.dumps({"version": 2, "lability_item_limit_ms": 4000, "future_key": "x"}),
        encoding="utf-8",
    )
    cfg = load_astur_timer_config(p)
    assert cfg.version == 2
    assert cfg.model_extra["future_key"] == "x"


def test_config_is_frozen() -> None:
    with pytest.raises(Exception):
        astur_timer_config.version = 999
