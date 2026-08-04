from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question
from app.schemas.question import QuestionResponse


async def get_all_questions(db: AsyncSession) -> list[QuestionResponse]:
    result = await db.execute(select(Question).order_by(Question.order))
    return [QuestionResponse.model_validate(q) for q in result.scalars().all()]
