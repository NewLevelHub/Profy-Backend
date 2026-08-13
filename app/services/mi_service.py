"""MI (Multiple-Intelligences-style) scoring — junior's (6-9) replacement
for RIASEC. No career matching and no hexagon-adjacency model here: junior
gets activities/clubs to try, not professions (TZ_Profi.md §4.1)."""

import uuid
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import AgeGroup
from app.models.question import Question, QuestionInstrument
from app.models.user_response import UserResponse
from app.services.age_tiers import visible_tiers
from app.services.mi_content import MI_ACTIVITIES

MI_ORDER: list[str] = [
    "verbal", "logical", "musical", "visual", "bodily",
    "interpersonal", "intrapersonal", "naturalistic",
]

# Answers at or below this value count as an explicit negative ("aversion").
_AVERSION_MAX_VALUE = 2

# Share of a category's answers that must be explicit negatives before that
# category is excluded from `strengths` even if it scores high — same
# convention as riasec_service._AVERSION_DISQUALIFY_RATIO.
_AVERSION_DISQUALIFY_RATIO = 0.3

# consistency() thresholds: with 8 unordered categories there's no hexagon
# model to reuse, so this is an explicit differentiation-based heuristic —
# not a validated psychometric measure.
_CONSISTENCY_HIGH_MIN = 40.0
_CONSISTENCY_MEDIUM_MIN = 20.0


async def question_counts(db: AsyncSession, age_group: AgeGroup) -> dict[str, int]:
    result = await db.execute(
        select(Question.mi_category, func.count(Question.id))
        .where(
            Question.instrument == QuestionInstrument.mi,
            Question.age_tier.in_(visible_tiers(age_group)),
        )
        .group_by(Question.mi_category)
    )
    counts = {t.value: c for t, c in result.all()}
    return {t: counts.get(t, 0) for t in MI_ORDER}


async def raw_scores(assessment_id: uuid.UUID, db: AsyncSession, age_group: AgeGroup) -> dict[str, int]:
    result = await db.execute(
        select(Question.mi_category, func.sum(UserResponse.answer_value))
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            UserResponse.assessment_id == assessment_id,
            Question.instrument == QuestionInstrument.mi,
            Question.age_tier.in_(visible_tiers(age_group)),
        )
        .group_by(Question.mi_category)
    )
    sums = {t.value: int(s) for t, s in result.all()}
    return {t: sums.get(t, 0) for t in MI_ORDER}


async def aversion(assessment_id: uuid.UUID, db: AsyncSession, age_group: AgeGroup) -> dict[str, int]:
    """Count of explicit-negative (<=2) answers per category."""
    result = await db.execute(
        select(Question.mi_category, func.count(UserResponse.id))
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            UserResponse.assessment_id == assessment_id,
            UserResponse.answer_value <= _AVERSION_MAX_VALUE,
            Question.instrument == QuestionInstrument.mi,
            Question.age_tier.in_(visible_tiers(age_group)),
        )
        .group_by(Question.mi_category)
    )
    counts = {t.value: c for t, c in result.all()}
    return {t: counts.get(t, 0) for t in MI_ORDER}


def normalize(raw: dict[str, int], counts: dict[str, int]) -> dict[str, float]:
    """% of the MAXIMUM POSSIBLE score for that category (count * 5) — see
    riasec_service.normalize, same convention."""
    return {
        t: round(raw.get(t, 0) / (counts[t] * 5) * 100, 1) if counts.get(t) else 0.0
        for t in MI_ORDER
    }


def differentiation(normalized: dict[str, float]) -> float:
    values = normalized.values()
    return round(max(values) - min(values), 1) if values else 0.0


def consistency(normalized: dict[str, float]) -> Literal["high", "medium", "low"]:
    spread = differentiation(normalized)
    if spread >= _CONSISTENCY_HIGH_MIN:
        return "high"
    if spread >= _CONSISTENCY_MEDIUM_MIN:
        return "medium"
    return "low"


def top_code(normalized: dict[str, float], limit: int = 3) -> list[str]:
    ranked = sorted(MI_ORDER, key=lambda t: (-normalized.get(t, 0.0), MI_ORDER.index(t)))
    return ranked[:limit]


def _aversion_ratio(category: str, aversion_counts: dict[str, int], counts: dict[str, int]) -> float:
    total = counts.get(category, 0)
    return (aversion_counts.get(category, 0) / total) if total else 0.0


def strengths_weaknesses(
    normalized: dict[str, float],
    aversion_counts: dict[str, int],
    counts: dict[str, int],
    limit: int = 3,
) -> tuple[list[str], list[str]]:
    ranked = sorted(MI_ORDER, key=lambda t: (-normalized.get(t, 0.0), MI_ORDER.index(t)))

    strengths = [
        t for t in ranked
        if _aversion_ratio(t, aversion_counts, counts) < _AVERSION_DISQUALIFY_RATIO
    ][:limit]
    if len(strengths) < limit:
        # See riasec_service.strengths_weaknesses's matching comment — a
        # strict aversion filter can leave too few (even zero) categories,
        # collapsing "Сильные стороны" to near-empty/empty. top_code above
        # already ignores aversion entirely; pad with the next best-scoring
        # categories regardless, up to `limit`.
        for t in ranked:
            if len(strengths) >= limit:
                break
            if t not in strengths:
                strengths.append(t)

    weaknesses = list(reversed(ranked))[:limit]

    return strengths, weaknesses


def development_plan(
    code: list[str],
    weaknesses: list[str],
    aversion_counts: dict[str, int],
    counts: dict[str, int],
) -> dict[str, list[str]]:
    """Same shape as riasec_service.development_plan, different content:
    clubs/activities to try, never professions."""
    reinforce: list[str] = []
    for category in code:
        reinforce.extend(MI_ACTIVITIES.get(category, [])[:2])

    compensate: list[str] = []
    for category in weaknesses:
        if _aversion_ratio(category, aversion_counts, counts) >= _AVERSION_DISQUALIFY_RATIO:
            continue
        compensate = MI_ACTIVITIES.get(category, [])[:2]
        break

    return {"reinforce": reinforce, "compensate": compensate}
