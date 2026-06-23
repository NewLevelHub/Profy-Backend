import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer import Answer
from app.models.assessment import Assessment
from app.models.question import Question, QuestionBlock
from app.schemas.answer import AnswerItem, AnswersResponse


async def save_answers(
    assessment_id: uuid.UUID,
    block: QuestionBlock,
    answers: list[AnswerItem],
    current_profile_id: uuid.UUID,
    db: AsyncSession,
) -> AnswersResponse:
    assessment_result = await db.execute(
        select(Assessment).where(Assessment.id == assessment_id)
    )
    assessment = assessment_result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    if assessment.profile_id != current_profile_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if answers:
        values = [
            {
                "id": uuid.uuid4(),
                "assessment_id": assessment_id,
                "question_id": item.question_id,
                "selected_option_index": item.selected_option_index,
            }
            for item in answers
        ]
        stmt = pg_insert(Answer).values(values).on_conflict_do_update(
            constraint="uq_answers_assessment_question",
            set_={"selected_option_index": pg_insert(Answer).excluded.selected_option_index},
        )
        await db.execute(stmt)

    distinct_blocks_result = await db.execute(
        select(func.count(func.distinct(Question.block)))
        .join(Answer, Answer.question_id == Question.id)
        .where(Answer.assessment_id == assessment_id)
    )
    distinct_blocks = distinct_blocks_result.scalar_one() or 0

    assessment.current_block = distinct_blocks
    await db.commit()
    await db.refresh(assessment)

    return AnswersResponse(saved=len(answers), current_block=assessment.current_block)
