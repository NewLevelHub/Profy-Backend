"""No DB involved — pure-function sten conversion + section shaping,
mirrors test_boyko_empathy_service.py's convention."""
from app.config import KondashAnxietyThresholds, KondashAgeBracket
from app.services import kondash_anxiety_service


def test_sten_from_raw_linear_interpolation_capped_at_10() -> None:
    # sten10 = 18 (15-16 лет bracket): step = 1.8 per sten
    assert kondash_anxiety_service.sten_from_raw(1, sten10=18) == 1  # ceil(1*10/18)=1
    assert kondash_anxiety_service.sten_from_raw(18, sten10=18) == 10  # exactly at the sten-10 threshold
    assert kondash_anxiety_service.sten_from_raw(9, sten10=18) == 5  # ceil(90/18)=5
    assert kondash_anxiety_service.sten_from_raw(40, sten10=18) == 10  # capped, theoretical max raw


def test_sten_from_raw_zero_raw_is_zero() -> None:
    assert kondash_anxiety_service.sten_from_raw(0, sten10=18) == 0


def test_build_confidence_data_none_when_no_raw_score() -> None:
    assert kondash_anxiety_service.build_confidence_data(None, age=16) is None


def test_build_confidence_data_shapes_sten_and_level() -> None:
    thresholds = KondashAnxietyThresholds(
        version=1,
        interpersonal_sten10_by_age=(KondashAgeBracket(max_age=16, sten10=18),),
        confidence_sten_bounds=(3, 6),
    )

    # raw=3 -> ceil(30/18)=2 -> "high" confidence
    data = kondash_anxiety_service.build_confidence_data(3, age=16, thresholds=thresholds)
    assert data == {"confidence_stens": 2, "confidence_level": "high"}

    # raw=9 -> ceil(90/18)=5 -> "normative"
    data = kondash_anxiety_service.build_confidence_data(9, age=16, thresholds=thresholds)
    assert data == {"confidence_stens": 5, "confidence_level": "normative"}

    # raw=18 -> sten 10 -> "low" confidence (elevated anxiety)
    data = kondash_anxiety_service.build_confidence_data(18, age=16, thresholds=thresholds)
    assert data == {"confidence_stens": 10, "confidence_level": "low"}


def test_build_confidence_data_uses_the_age_appropriate_bracket() -> None:
    thresholds = KondashAnxietyThresholds(
        version=1,
        interpersonal_sten10_by_age=(
            KondashAgeBracket(max_age=14, sten10=28),
            KondashAgeBracket(max_age=16, sten10=18),
        ),
        confidence_sten_bounds=(3, 6),
    )

    # Same raw score, different age brackets -> different sten.
    at_14 = kondash_anxiety_service.build_confidence_data(14, age=14, thresholds=thresholds)
    at_16 = kondash_anxiety_service.build_confidence_data(14, age=16, thresholds=thresholds)

    assert at_14["confidence_stens"] == 5  # ceil(140/28)=5
    assert at_16["confidence_stens"] == 8  # ceil(140/18)=8
