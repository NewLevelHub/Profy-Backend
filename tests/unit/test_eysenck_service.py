"""No DB involved — pure-function section shaping, mirrors
test_professional_types_service.py's convention."""
from app.config import EysenckThresholds
from app.services import eysenck_service


def test_build_section_data_none_when_no_scores() -> None:
    assert eysenck_service.build_section_data(None) is None


def test_build_section_data_shapes_raw_scores_into_levels_and_flag() -> None:
    thresholds = EysenckThresholds(
        version=1, lie_scale_max_ok=4,
        extraversion_bounds=(4, 8, 14, 19), neuroticism_bounds=(8, 13, 19),
    )
    scores = {"extraversion": 20, "neuroticism": 5, "lie": 6}

    data = eysenck_service.build_section_data(scores, thresholds=thresholds)

    assert data == {
        "extraversion_raw": 20,
        "neuroticism_raw": 5,
        "lie_scale_raw": 6,
        "extraversion_level": "bright_extravert",
        "neuroticism_level": "low",
        "protocol_flagged": True,
        "quadrant": "sanguine",
    }


def test_build_section_data_protocol_not_flagged_at_the_ok_boundary() -> None:
    thresholds = EysenckThresholds(
        version=1, lie_scale_max_ok=4,
        extraversion_bounds=(4, 8, 14, 19), neuroticism_bounds=(8, 13, 19),
    )
    scores = {"extraversion": 10, "neuroticism": 10, "lie": 4}

    data = eysenck_service.build_section_data(scores, thresholds=thresholds)

    assert data["protocol_flagged"] is False


def test_quadrant_maps_all_four_classic_eysenck_temperaments() -> None:
    assert eysenck_service.quadrant(20, 20) == "choleric"  # extravert + unstable
    assert eysenck_service.quadrant(20, 5) == "sanguine"  # extravert + stable
    assert eysenck_service.quadrant(5, 5) == "phlegmatic"  # introvert + stable
    assert eysenck_service.quadrant(5, 20) == "melancholic"  # introvert + unstable


def test_quadrant_ties_at_the_midpoint_fall_on_the_extravert_unstable_side() -> None:
    assert eysenck_service.quadrant(12, 12) == "choleric"
    assert eysenck_service.quadrant(11, 12) == "melancholic"
    assert eysenck_service.quadrant(12, 11) == "sanguine"
