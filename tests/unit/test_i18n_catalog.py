"""KZ-307 — `app/i18n/catalog/` resolver: request-locale resolution, per-key
`ru` fallback with a recorded tally, and shape parity between RU and KK trees.
"""

import pytest

from app import i18n
from app.i18n.catalog import _AREAS, key, tr


@pytest.fixture(autouse=True)
def _reset():
    i18n.reset_fallback_counts()
    i18n._current_locale.set(i18n.DEFAULT_LOCALE)
    yield
    i18n.reset_fallback_counts()
    i18n._current_locale.set(i18n.DEFAULT_LOCALE)


@pytest.mark.parametrize("area", list(_AREAS))
def test_ru_and_kk_trees_have_the_same_shape(area: str) -> None:
    """Every RU top-level key exists in KK, and nested dict sub-keys match too
    (so `kk` never silently drops a label). Lists just need equal length."""
    mod = _AREAS[area]
    ru, kk = mod.RU, mod.KK
    assert set(kk) == set(ru), f"{area}: KK top-level keys != RU"
    for k, ru_val in ru.items():
        kk_val = kk[k]
        assert type(ru_val) is type(kk_val), f"{area}.{k}: type mismatch"
        if isinstance(ru_val, dict):
            assert set(_flatten(ru_val)) == set(_flatten(kk_val)), f"{area}.{k}: nested key drift"
        elif isinstance(ru_val, list):
            assert len(ru_val) == len(kk_val), f"{area}.{k}: list length differs"


def _flatten(d: dict, prefix: str = "") -> list[str]:
    out: list[str] = []
    for k, v in d.items():
        p = f"{prefix}.{k}" if prefix else k
        out.extend(_flatten(v, p) if isinstance(v, dict) else [p])
    return out


def test_default_locale_returns_ru_and_records_nothing() -> None:
    assert tr("riasec")["labels"]["R"] == "Реалистичный"
    assert i18n.fallback_counts() == {}


def test_kk_locale_returns_kk() -> None:
    i18n._current_locale.set("kk")
    assert tr("riasec")["labels"]["R"] == "Реалистік"
    assert key("mi", "labels", "verbal") == "Сөздер мен әңгімелер"
    assert i18n.fallback_counts() == {}  # riasec/mi fully translated


def test_missing_kk_key_falls_back_to_ru_and_is_recorded(monkeypatch) -> None:
    from app.i18n.catalog import riasec as riasec_area

    trimmed = dict(riasec_area.KK)
    trimmed.pop("neutral_try_now")
    monkeypatch.setattr(riasec_area, "KK", trimmed)
    i18n._current_locale.set("kk")

    table = tr("riasec")
    assert table["labels"]["R"] == "Реалистік"  # still kk
    assert table["neutral_try_now"] == riasec_area.RU["neutral_try_now"]  # ru fallback
    assert i18n.fallback_counts().get("kk") == 1


def test_explicit_locale_arg_overrides_request_locale() -> None:
    i18n._current_locale.set("kk")
    assert tr("riasec", locale="ru")["labels"]["R"] == "Реалистичный"


def test_deterministic_report_pieces_follow_the_request_locale() -> None:
    """A consumer service (not just the catalog) yields `kk` under `kk`."""
    from app.services import mi_service, riasec_service
    from app.services.motivation_content import highlight_phrases

    ru_plan = riasec_service.development_plan(["R"], [], {}, {"R": 4})
    ru_mi = mi_service.development_plan(["logical"], [], {}, {"logical": 4})
    ru_drivers = highlight_phrases(["interest"])

    i18n._current_locale.set("kk")
    kk_plan = riasec_service.development_plan(["R"], [], {}, {"R": 4})
    kk_mi = mi_service.development_plan(["logical"], [], {}, {"logical": 4})
    kk_drivers = highlight_phrases(["interest"])

    assert kk_plan["reinforce"] and kk_plan["reinforce"] != ru_plan["reinforce"]
    assert kk_mi["reinforce"] and kk_mi["reinforce"] != ru_mi["reinforce"]
    assert kk_drivers and kk_drivers != ru_drivers
    assert "жұмыс" in " ".join(kk_drivers) or "қызық" in " ".join(kk_drivers)
