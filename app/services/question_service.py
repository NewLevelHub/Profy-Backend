from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import pick_locale
from app.models.profile import AgeGroup
from app.models.question import Question, QuestionInstrument
from app.schemas.question import QuestionResponse
from app.services.age_tiers import visible_tiers


def to_response_schema(question: Question, locale: str | None = None) -> QuestionResponse:
    return QuestionResponse(
        id=question.id,
        instrument=question.instrument,
        riasec_type=question.riasec_type,
        bigfive_domain=question.bigfive_domain,
        text=pick_locale(question.text, locale),
        order=question.order,
    )


async def get_all_questions(db: AsyncSession, age_group: AgeGroup) -> list[QuestionResponse]:
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
    return [to_response_schema(q) for q in result.scalars().all()]
