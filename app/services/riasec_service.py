"""RIASEC scoring, meta-characteristics, and career matching — see riasec-methodology.md."""

import uuid
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.direction import Direction
from app.models.profile import AgeGroup
from app.models.question import HollandType, Question, QuestionInstrument
from app.models.user_response import UserResponse
from app.services.age_tiers import visible_tiers
from app.services.riasec_content import TYPE_ACTIVITIES

HOLLAND_ORDER: list[str] = ["R", "I", "A", "S", "E", "C"]

# Answers at or below this value count as an explicit negative ("aversion").
_AVERSION_MAX_VALUE = 2

# Share of a type's answers that must be explicit negatives before that type
# is excluded from `strengths` even if it scores high (methodology §5.3: a
# strength must be a "устойчивый, непротиворечивый интерес").
_AVERSION_DISQUALIFY_RATIO = 0.3


async def question_counts(db: AsyncSession, age_group: AgeGroup) -> dict[str, int]:
    """Questions per type, scoped to what this age branch was actually shown
    — computed live, never hardcoded (bank/age tiering can change size)."""
    result = await db.execute(
        select(Question.riasec_type, func.count(Question.id))
        .where(
            Question.instrument == QuestionInstrument.riasec,
            Question.age_tier.in_(visible_tiers(age_group)),
        )
        .group_by(Question.riasec_type)
    )
    counts = {t.value: c for t, c in result.all()}
    return {t: counts.get(t, 0) for t in HOLLAND_ORDER}


async def raw_scores(assessment_id: uuid.UUID, db: AsyncSession, age_group: AgeGroup) -> dict[str, int]:
    result = await db.execute(
        select(Question.riasec_type, func.sum(UserResponse.answer_value))
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            UserResponse.assessment_id == assessment_id,
            Question.instrument == QuestionInstrument.riasec,
            Question.age_tier.in_(visible_tiers(age_group)),
        )
        .group_by(Question.riasec_type)
    )
    sums = {t.value: int(s) for t, s in result.all()}
    return {t: sums.get(t, 0) for t in HOLLAND_ORDER}


async def aversion(assessment_id: uuid.UUID, db: AsyncSession, age_group: AgeGroup) -> dict[str, int]:
    """Count of explicit-negative (<=2) answers per type."""
    result = await db.execute(
        select(Question.riasec_type, func.count(UserResponse.id))
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            UserResponse.assessment_id == assessment_id,
            UserResponse.answer_value <= _AVERSION_MAX_VALUE,
            Question.instrument == QuestionInstrument.riasec,
            Question.age_tier.in_(visible_tiers(age_group)),
        )
        .group_by(Question.riasec_type)
    )
    counts = {t.value: c for t, c in result.all()}
    return {t: counts.get(t, 0) for t in HOLLAND_ORDER}


def normalize(raw: dict[str, int], counts: dict[str, int]) -> dict[str, float]:
    """% of the MAXIMUM POSSIBLE score for that type (count * 5) — not self-relative.

    This differs deliberately from the old engine's normalize_scores(), which scaled
    against the student's own top category (always 100%). Here 100% means "answered
    the maximum on every question of this type" — a student may never hit it."""
    return {
        t: round(raw.get(t, 0) / (counts[t] * 5) * 100, 1) if counts.get(t) else 0.0
        for t in HOLLAND_ORDER
    }


def differentiation(normalized: dict[str, float]) -> float:
    values = normalized.values()
    return round(max(values) - min(values), 1) if values else 0.0


def _hexagon_distance(a: str, b: str) -> int:
    i, j = HOLLAND_ORDER.index(a), HOLLAND_ORDER.index(b)
    diff = abs(i - j)
    return min(diff, len(HOLLAND_ORDER) - diff)


def consistency(top2: list[str]) -> Literal["high", "medium", "low"]:
    if len(top2) < 2:
        return "high"
    distance = _hexagon_distance(top2[0], top2[1])
    if distance <= 1:
        return "high"
    if distance == 2:
        return "medium"
    return "low"


def top_code(normalized: dict[str, float], limit: int = 3) -> list[str]:
    # Tie-break: fixed HOLLAND_ORDER position, so equal percentages are still
    # resolved deterministically (methodology §3, step 4).
    ranked = sorted(HOLLAND_ORDER, key=lambda t: (-normalized.get(t, 0.0), HOLLAND_ORDER.index(t)))
    return ranked[:limit]


def career_match_score(user_code: list[str], direction_code: str) -> int:
    weights = [3, 2, 1]
    return sum(w for w, letter in zip(weights, user_code) if letter in direction_code)


async def matched_careers(
    user_code: list[str], db: AsyncSession, limit: int = 10
) -> list[tuple[Direction, int]]:
    result = await db.execute(select(Direction))
    directions = list(result.scalars().all())
    scored = [(d, career_match_score(user_code, d.holland_code)) for d in directions]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]


def _aversion_ratio(letter: str, aversion_counts: dict[str, int], counts: dict[str, int]) -> float:
    total = counts.get(letter, 0)
    return (aversion_counts.get(letter, 0) / total) if total else 0.0


def strengths_weaknesses(
    normalized: dict[str, float],
    aversion_counts: dict[str, int],
    counts: dict[str, int],
    limit: int = 3,
) -> tuple[list[str], list[str]]:
    ranked = sorted(HOLLAND_ORDER, key=lambda t: (-normalized.get(t, 0.0), HOLLAND_ORDER.index(t)))

    strengths = [
        t for t in ranked
        if _aversion_ratio(t, aversion_counts, counts) < _AVERSION_DISQUALIFY_RATIO
    ][:limit]

    weaknesses = list(reversed(ranked))[:limit]

    return strengths, weaknesses


def development_plan(
    code: list[str],
    weaknesses: list[str],
    aversion_counts: dict[str, int],
    counts: dict[str, int],
) -> dict[str, list[str]]:
    """Methodology §5.4: reinforce the top code, offer a compensating activity for
    the single weakest type — unless the student explicitly dislikes it (aversion)."""
    reinforce: list[str] = []
    for letter in code:
        reinforce.extend(TYPE_ACTIVITIES.get(letter, [])[:2])

    compensate: list[str] = []
    for letter in weaknesses:
        if _aversion_ratio(letter, aversion_counts, counts) >= _AVERSION_DISQUALIFY_RATIO:
            continue
        compensate = TYPE_ACTIVITIES.get(letter, [])[:2]
        break

    return {"reinforce": reinforce, "compensate": compensate}
