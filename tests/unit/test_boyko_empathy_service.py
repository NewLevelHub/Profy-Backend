"""No DB involved — pure-function section shaping, mirrors
test_eysenck_service.py's/test_elers_service.py's convention."""
from app.config import BoykoEmpathyThresholds
from app.services import boyko_empathy_service


def test_build_section_data_none_when_no_scores() -> None:
    assert boyko_empathy_service.build_section_data(None) is None


def test_build_section_data_sums_channels_into_total_and_level() -> None:
    thresholds = BoykoEmpathyThresholds(version=1, bounds=(14, 21, 29))
    scores = {
        "rational": 4, "emotional": 5, "intuitive": 5,
        "attitudes": 5, "penetration": 5, "identification": 6,
    }  # sum = 30

    data = boyko_empathy_service.build_section_data(scores, thresholds=thresholds)

    assert data == {
        "empathy_channels": scores,
        "empathy_total": 30,
        "empathy_level": "very_high",
    }


def test_build_section_data_at_the_ambiguous_boundary_score_14() -> None:
    thresholds = BoykoEmpathyThresholds(version=1, bounds=(14, 21, 29))
    scores = {
        "rational": 3, "emotional": 3, "intuitive": 2,
        "attitudes": 2, "penetration": 2, "identification": 2,
    }  # sum = 14

    data = boyko_empathy_service.build_section_data(scores, thresholds=thresholds)

    assert data["empathy_total"] == 14
    assert data["empathy_level"] == "very_low"
