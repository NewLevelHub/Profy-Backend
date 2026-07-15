import pytest

from app.core.axes import (
    AXIS_CATALOG,
    AXIS_CODES,
    AxisFamily,
    format_for_axis,
    is_valid_axis,
)


def test_catalog_has_24_axes():
    assert len(AXIS_CATALOG) == 24
    assert len(AXIS_CODES) == 24


def test_no_duplicate_codes():
    codes = [axis.code for axis in AXIS_CATALOG]
    assert len(codes) == len(set(codes))


def test_covers_5_families_with_expected_sizes():
    counts = {family: 0 for family in AxisFamily}
    for axis in AXIS_CATALOG:
        counts[axis.family] += 1
    assert counts == {
        AxisFamily.A: 5,
        AxisFamily.B: 6,
        AxisFamily.C: 3,
        AxisFamily.D: 7,
        AxisFamily.E: 3,
    }


def test_every_axis_has_a_non_empty_label():
    for axis in AXIS_CATALOG:
        assert axis.label_ru.strip()


@pytest.mark.parametrize("code", ["People", "Care", "Predict", "Math"])
def test_is_valid_axis_accepts_known_codes(code):
    assert is_valid_axis(code)


def test_is_valid_axis_rejects_unknown_or_legacy_codes():
    assert not is_valid_axis("A_people")
    assert not is_valid_axis("B_analyze")
    assert not is_valid_axis("unknown")


def test_format_for_axis_a_and_e_are_always_direct():
    assert format_for_axis("People", depth=0) == "direct"
    assert format_for_axis("People", depth=5) == "direct"
    assert format_for_axis("Math", depth=5) == "direct"


def test_format_for_axis_d_is_always_situational():
    assert format_for_axis("Focus", depth=0) == "situational"
    assert format_for_axis("Focus", depth=5) == "situational"


def test_format_for_axis_b_and_c_are_depth_dependent():
    assert format_for_axis("Inv", depth=0) == "direct"
    assert format_for_axis("Inv", depth=1) == "direct"
    assert format_for_axis("Inv", depth=2) == "situational"
    assert format_for_axis("Motor", depth=1) == "direct"
    assert format_for_axis("Motor", depth=3) == "situational"


def test_format_for_axis_rejects_unknown_code():
    with pytest.raises(ValueError):
        format_for_axis("not_an_axis", depth=0)
