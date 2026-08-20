"""Big Five (IPIP-NEO-120 Johnson) scoring — domain and facet raw/normalized scores.

Mirrors riasec_service.py's shape (question_counts/raw_scores/normalize), plus
facet-level scoring feeding thinking_style_service.py."""

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import AgeGroup
from app.models.question import Keyed, Question, QuestionInstrument
from app.models.user_response import UserResponse
from app.services.age_tiers import visible_tiers

BIGFIVE_ORDER: list[str] = ["N", "E", "O", "A", "C"]

# Reverse-keyed items are inverted at read time (never at storage): a `minus`
# item's contribution is (6 - answer_value), so higher always means "more of
# the trait" regardless of how the statement was phrased.
_SCORE_EXPR = case(
    (Question.keyed == Keyed.minus, 6 - UserResponse.answer_value),
    else_=UserResponse.answer_value,
)


async def question_counts(db: AsyncSession, age_group: AgeGroup) -> dict[str, int]:
    """Questions per domain, scoped to what this age branch was actually
    shown — computed live, never hardcoded (bank/age tiering can change size)."""
    result = await db.execute(
        select(Question.bigfive_domain, func.count(Question.id))
        .where(
            Question.instrument == QuestionInstrument.big_five,
            Question.age_tier.in_(visible_tiers(age_group)),
        )
        .group_by(Question.bigfive_domain)
    )
    counts = {d.value: c for d, c in result.all()}
    return {d: counts.get(d, 0) for d in BIGFIVE_ORDER}


async def raw_scores(assessment_id: uuid.UUID, db: AsyncSession, age_group: AgeGroup) -> dict[str, int]:
    result = await db.execute(
        select(Question.bigfive_domain, func.sum(_SCORE_EXPR))
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            UserResponse.assessment_id == assessment_id,
            Question.instrument == QuestionInstrument.big_five,
            Question.age_tier.in_(visible_tiers(age_group)),
        )
        .group_by(Question.bigfive_domain)
    )
    sums = {d.value: int(s) for d, s in result.all()}
    return {d: sums.get(d, 0) for d in BIGFIVE_ORDER}


def normalize(raw: dict[str, int], counts: dict[str, int]) -> dict[str, float]:
    """% between the MINIMUM and MAXIMUM possible score for that domain. Each
    item is answered on a 1-5 scale (never 0), so the true floor is count*1,
    not 0 — using 0 as the floor compresses/shifts the whole range toward the
    top. min-max: (raw - count) / (count*4) * 100."""
    return {
        d: round((raw.get(d, 0) - counts[d]) / (counts[d] * 4) * 100, 1) if counts.get(d) else 0.0
        for d in BIGFIVE_ORDER
    }


async def facet_raw(
    assessment_id: uuid.UUID, db: AsyncSession, age_group: AgeGroup
) -> dict[tuple[str, int], int]:
    result = await db.execute(
        select(Question.bigfive_domain, Question.facet, func.sum(_SCORE_EXPR))
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            UserResponse.assessment_id == assessment_id,
            Question.instrument == QuestionInstrument.big_five,
            Question.age_tier.in_(visible_tiers(age_group)),
        )
        .group_by(Question.bigfive_domain, Question.facet)
    )
    return {(d.value, f): int(s) for d, f, s in result.all()}


async def facet_counts(db: AsyncSession, age_group: AgeGroup) -> dict[tuple[str, int], int]:
    result = await db.execute(
        select(Question.bigfive_domain, Question.facet, func.count(Question.id))
        .where(
            Question.instrument == QuestionInstrument.big_five,
            Question.age_tier.in_(visible_tiers(age_group)),
        )
        .group_by(Question.bigfive_domain, Question.facet)
    )
    return {(d.value, f): c for d, f, c in result.all()}


def facet_normalize(
    raw: dict[tuple[str, int], int], counts: dict[tuple[str, int], int]
) -> dict[tuple[str, int], float]:
    """min-max, see normalize() above for why the floor is count*1, not 0."""
    return {
        key: round((raw.get(key, 0) - count) / (count * 4) * 100, 1) if count else 0.0
        for key, count in counts.items()
    }
