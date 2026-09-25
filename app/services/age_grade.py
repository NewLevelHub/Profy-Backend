"""Age ↔ school-grade pairing (PRO-420).

Kazakh/Russian school calendar: grade 1 typically starts around 6–7, so
`age - grade` lands near 5–7 for most students. Allow ± a year of slack
(repeaters / early starts) → delta in [5, 8]. Rejects pairs like 17 + 3.
"""

from __future__ import annotations

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
    allowed = grades_for_age(age)
    if not allowed:
        return f"age {age} has no compatible school grade"
    lo, hi = allowed[0], allowed[-1]
    return (
        f"age {age} is incompatible with grade {grade}; "
        f"expected grade {lo}–{hi} (age − grade between "
        f"{MIN_AGE_MINUS_GRADE} and {MAX_AGE_MINUS_GRADE})"
    )
