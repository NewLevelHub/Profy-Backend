"""No DB involved — pure-function section shaping, mirrors
test_eysenck_service.py's convention."""
from app.config import ElersThresholds
from app.services import elers_service


def test_build_section_data_none_when_no_score() -> None:
    assert elers_service.build_section_data(None) is None


def test_build_section_data_shapes_score_into_level() -> None:
    thresholds = ElersThresholds(version=1, bounds=(10, 16, 20))

    assert elers_service.build_section_data(5, thresholds=thresholds) == {"score": 5, "level": "low"}
    assert elers_service.build_section_data(16, thresholds=thresholds) == {"score": 16, "level": "medium"}
    assert elers_service.build_section_data(20, thresholds=thresholds) == {
        "score": 20,
        "level": "moderately_high",
    }
    assert elers_service.build_section_data(25, thresholds=thresholds) == {"score": 25, "level": "too_high"}
