from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import AgeGroup
from app.models.question import Question
from app.schemas.question import QuestionResponse
from app.services.age_tiers import visible_tiers


async def get_all_questions(db: AsyncSession, age_group: AgeGroup) -> list[QuestionResponse]:
    result = await db.execute(
        select(Question)
        .where(Question.age_tier.in_(visible_tiers(age_group)))
        .order_by(Question.order)
    )
    return [QuestionResponse.model_validate(q) for q in result.scalars().all()]
