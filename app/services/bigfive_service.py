"""Big Five (IPIP-NEO-120 Johnson) scoring — domain and facet raw/normalized scores.

Mirrors riasec_service.py's shape (question_counts/raw_scores/normalize), plus
facet-level scoring feeding thinking_style_service.py.

Response-style (acquiescence) correction
----------------------------------------
IPIP-NEO-120 is NOT keyed-balanced per domain (N 17+/7-, E 18+/6-, A 7+/17-,
O 12/12, C 11/13). With plain min-max scoring and no population norms, a
respondent's habitual tendency to agree (or disagree) with statements
regardless of content then leaks straight into the domain %: a "yea-sayer"
scores A artificially low and N artificially high, purely from response
style. `raw_scores`/`facet_raw` subtract that out per respondent — see
`_acquiescence_shift`. A balanced domain (plus == minus) is untouched; the
shift is exactly 0 when the respondent's mean answer is the scale midpoint.
"""

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import AgeGroup
from app.models.question import Keyed, Question, QuestionInstrument
from app.models.user_response import UserResponse
from app.services.age_tiers import visible_tiers

BIGFIVE_ORDER: list[str] = ["N", "E", "O", "A", "C"]

_SCALE_MIDPOINT = 3.0  # the "3" of the fixed 1-5 answer scale

# Reverse-keyed items are inverted at read time (never at storage): a `minus`
# item's contribution is (6 - answer_value), so higher always means "more of
# the trait" regardless of how the statement was phrased.
_SCORE_EXPR = case(
    (Question.keyed == Keyed.minus, 6 - UserResponse.answer_value),
    else_=UserResponse.answer_value,
)


def _acquiescence_shift(minus_count: int, plus_count: int, mean_answer: float) -> float:
    """How much a respondent's answer style has displaced this domain's (or
    facet's) raw sum, given `minus_count` reverse-keyed and `plus_count`
    forward-keyed items in it.

    Corrected answer a' = a - (mean_answer - 3). Substituting into the raw
    sum (plus items contribute a, minus items contribute 6 - a) and
    simplifying, the whole per-item (mean_answer - 3) offset cancels on the
    forward items and doubles-back on the reverse items, leaving exactly
    (minus_count - plus_count) * (mean_answer - 3). Zero when the item set
    is balanced, or when the respondent answered at the midpoint on average.
    """
    return (minus_count - plus_count) * (mean_answer - _SCALE_MIDPOINT)


async def _grand_mean(assessment_id: uuid.UUID, db: AsyncSession, age_group: AgeGroup) -> float:
    """Respondent's mean answer (raw 1-5, before reverse-keying) across every
    Big Five item they were shown — the acquiescence estimate. Midpoint
    (3.0) when there are no responses, so the correction is a no-op."""
    result = await db.execute(
        select(func.avg(UserResponse.answer_value))
        .join(Question, UserResponse.question_id == Question.id)
        .where(
            UserResponse.assessment_id == assessment_id,
            Question.instrument == QuestionInstrument.big_five,
            Question.age_tier.in_(visible_tiers(age_group)),
        )
    )
    avg = result.scalar_one_or_none()
    return float(avg) if avg is not None else _SCALE_MIDPOINT


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


async def keying_counts(db: AsyncSession, age_group: AgeGroup) -> dict[str, tuple[int, int]]:
    """(plus_count, minus_count) per domain for the items this age branch was
    shown — live from the bank, same rationale as `question_counts`. Feeds
    the acquiescence correction in `raw_scores`."""
    result = await db.execute(
        select(Question.bigfive_domain, Question.keyed, func.count(Question.id))
        .where(
            Question.instrument == QuestionInstrument.big_five,
            Question.age_tier.in_(visible_tiers(age_group)),
        )
        .group_by(Question.bigfive_domain, Question.keyed)
    )
    plus: dict[str, int] = {}
    minus: dict[str, int] = {}
    for domain, keyed, count in result.all():
        (minus if keyed == Keyed.minus else plus)[domain.value] = count
    return {d: (plus.get(d, 0), minus.get(d, 0)) for d in BIGFIVE_ORDER}


async def facet_keying_counts(
    db: AsyncSession, age_group: AgeGroup
) -> dict[tuple[str, int], tuple[int, int]]:
    """(plus_count, minus_count) per (domain, facet) — facet-level counterpart
    of `keying_counts`, feeding the acquiescence correction in `facet_raw`."""
    result = await db.execute(
        select(Question.bigfive_domain, Question.facet, Question.keyed, func.count(Question.id))
        .where(
            Question.instrument == QuestionInstrument.big_five,
            Question.age_tier.in_(visible_tiers(age_group)),
        )
        .group_by(Question.bigfive_domain, Question.facet, Question.keyed)
    )
    plus: dict[tuple[str, int], int] = {}
    minus: dict[tuple[str, int], int] = {}
    for domain, facet, keyed, count in result.all():
        (minus if keyed == Keyed.minus else plus)[(domain.value, facet)] = count
    keys = set(plus) | set(minus)
    return {k: (plus.get(k, 0), minus.get(k, 0)) for k in keys}


async def raw_scores(
    assessment_id: uuid.UUID, db: AsyncSession, age_group: AgeGroup
) -> dict[str, float]:
    """Per-domain reverse-keyed sum, then acquiescence-corrected (see module
    docstring). Float, not int, because the correction is fractional."""
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
    sums = {d.value: float(s) for d, s in result.all()}

    mean_answer = await _grand_mean(assessment_id, db, age_group)
    keying = await keying_counts(db, age_group)
    return {
        d: sums.get(d, 0.0) + _acquiescence_shift(keying[d][1], keying[d][0], mean_answer)
        for d in BIGFIVE_ORDER
    }


def normalize(raw: dict[str, float], counts: dict[str, int]) -> dict[str, float]:
    """% between the MINIMUM and MAXIMUM possible score for that domain. Each
    item is answered on a 1-5 scale (never 0), so the true floor is count*1,
    not 0 — using 0 as the floor compresses/shifts the whole range toward the
    top. min-max: (raw - count) / (count*4) * 100. Clamped to [0, 100] — the
    acquiescence correction can push an extreme responder's corrected sum a
    hair past the theoretical bounds."""
    return {
        d: _clamp(round((raw.get(d, 0.0) - counts[d]) / (counts[d] * 4) * 100, 1))
        if counts.get(d)
        else 0.0
        for d in BIGFIVE_ORDER
    }


def _clamp(value: float) -> float:
    return min(100.0, max(0.0, value))


async def facet_raw(
    assessment_id: uuid.UUID, db: AsyncSession, age_group: AgeGroup
) -> dict[tuple[str, int], float]:
    """Per-(domain, facet) reverse-keyed sum, acquiescence-corrected with the
    facet-level keying split — same treatment as `raw_scores`."""
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
    sums = {(d.value, f): float(s) for d, f, s in result.all()}

    mean_answer = await _grand_mean(assessment_id, db, age_group)
    keying = await facet_keying_counts(db, age_group)
    return {
        key: total + _acquiescence_shift(keying.get(key, (0, 0))[1], keying.get(key, (0, 0))[0], mean_answer)
        for key, total in sums.items()
    }


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
    raw: dict[tuple[str, int], float], counts: dict[tuple[str, int], int]
) -> dict[tuple[str, int], float]:
    """min-max, see normalize() above for why the floor is count*1, not 0, and
    why the result is clamped."""
    return {
        key: _clamp(round((raw.get(key, 0.0) - count) / (count * 4) * 100, 1)) if count else 0.0
        for key, count in counts.items()
    }
