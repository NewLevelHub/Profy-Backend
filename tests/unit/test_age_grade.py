"""Age ↔ grade pairing (PRO-420)."""

from app.services.age_grade import (
    MAX_AGE_MINUS_GRADE,
    MIN_AGE_MINUS_GRADE,
    grades_for_age,
    is_age_grade_compatible,
)


def test_rejects_seventeen_in_third_grade() -> None:
    assert not is_age_grade_compatible(17, 3)


def test_accepts_typical_senior_pairs() -> None:
    assert is_age_grade_compatible(15, 9)
    assert is_age_grade_compatible(16, 10)
    assert is_age_grade_compatible(17, 11)
    assert is_age_grade_compatible(18, 12)


def test_delta_bounds() -> None:
    # age - grade == 5 and == 8 are inclusive edges
    assert is_age_grade_compatible(14, 9)  # delta 5
    assert is_age_grade_compatible(14, 6)  # delta 8
    assert not is_age_grade_compatible(14, 10)  # delta 4
    assert not is_age_grade_compatible(14, 5)  # delta 9


def test_grades_for_age_seventeen() -> None:
    assert grades_for_age(17) == [9, 10, 11, 12]
    assert MIN_AGE_MINUS_GRADE == 5
    assert MAX_AGE_MINUS_GRADE == 8
