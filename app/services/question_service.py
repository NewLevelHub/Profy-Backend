from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import AgeGroup
from app.models.question import Question, QuestionInstrument
from app.schemas.question import QuestionResponse
from app.services.age_tiers import visible_tiers
from app.services.content_locale import localized_rows


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
    # Display path: request locale, per-question fallback to `ru` (KZ-301).
    questions = await localized_rows(db, query, Question, key="order")
    return [QuestionResponse.model_validate(q) for q in questions]
