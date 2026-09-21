import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import pick_locale
from app.models.profile import AgeGroup
from app.models.question import Question, QuestionInstrument
from app.schemas.question import QuestionResponse
from app.services.age_tiers import visible_tiers
def _bigfive_scale(question: Question) -> bool:
    return question.instrument == QuestionInstrument.big_five


def to_response_schema(
    question: Question, order: int | None = None, locale: str | None = None
) -> QuestionResponse:

    return QuestionResponse(
        id=question.id,
        instrument=question.instrument,
        riasec_type=question.riasec_type,
        bigfive_domain=question.bigfive_domain,
        text=pick_locale(question.text, locale),
        order=order if order is not None else question.order,
        bigfive_scale=_bigfive_scale(question),
    )


# Backwards-compatible alias — the validity-interleave splicing (PRO-298)
# below always calls with an explicit renumbered `order`.
_to_response = to_response_schema


async def get_all_questions(
    db: AsyncSession,
    age_group: AgeGroup,
    *,
    assessment_id: uuid.UUID | None = None,
    locale: str | None = None,
) -> list[QuestionResponse]:
    """The Likert battery for one assessment."""
    query = (
        select(Question)
        .where(Question.age_tier.in_(visible_tiers(age_group)))
        .order_by(Question.order)
    )
    if age_group == AgeGroup.junior:
        # Junior's stale `riasec`-tagged rows (retired in favor of MI, see
        # question_pair_service.get_pairs) would otherwise leak into the
        # plain Likert flow now that junior answers MI here too.
        query = query.where(Question.instrument != QuestionInstrument.riasec)
    result = await db.execute(query)
    questions = list(result.scalars().all())

    return [to_response_schema(q, i + 1, locale) for i, q in enumerate(questions)]
