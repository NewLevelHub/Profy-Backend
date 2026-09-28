"""Age ↔ school-grade pairing (PRO-420).

Kazakh/Russian school calendar: grade 1 typically starts around 6–7, so
`age - grade` lands near 5–7 for most students. Allow ± a year of slack
(repeaters / early starts) → delta in [5, 8]. Rejects pairs like 17 + 3.
"""

from __future__ import annotations

from app.i18n.catalog import key as i18n_key

# Inclusive bounds on (age - grade).
MIN_AGE_MINUS_GRADE = 5
MAX_AGE_MINUS_GRADE = 8

GRADE_MIN = 1
GRADE_MAX = 12


def is_age_grade_compatible(age: int, grade: int) -> bool:
    if not (GRADE_MIN <= grade <= GRADE_MAX):
        return False
    delta = age - grade
    return MIN_AGE_MINUS_GRADE <= delta <= MAX_AGE_MINUS_GRADE


def grades_for_age(age: int) -> list[int]:
    return [g for g in range(GRADE_MIN, GRADE_MAX + 1) if is_age_grade_compatible(age, g)]


def age_grade_mismatch_message(age: int, grade: int) -> str:
    """In the request locale — resolved at call time, never at import."""
    allowed = grades_for_age(age)
    if not allowed:
        return i18n_key("api_errors", "age_has_no_compatible_grade").format(age=age)
    return i18n_key("api_errors", "age_grade_mismatch").format(
        age=age,
        grade=grade,
        lo=allowed[0],
        hi=allowed[-1],
        min_delta=MIN_AGE_MINUS_GRADE,
        max_delta=MAX_AGE_MINUS_GRADE,
    )
