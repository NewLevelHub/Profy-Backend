import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.question import Question, QuestionBlock
from app.schemas.question import QuestionOption, QuestionResponse
from app.services.scoring_service import LIKERT_LABELS, is_likert_question


def _to_response(question: Question) -> QuestionResponse:
    if is_likert_question(question.options):
        options = [
            QuestionOption(text=label, index=i)
            for i, label in enumerate(LIKERT_LABELS)
        ]
    else:
        options = [
            QuestionOption(text=opt["text"], index=i)
            for i, opt in enumerate(question.options)
        ]
    return QuestionResponse(
        id=question.id,
        block=question.block,
        text=question.text,
        options=options,
    )


async def get_questions_for_block(
    assessment_id: uuid.UUID,
    block: QuestionBlock,
    current_profile_id: uuid.UUID,
    db: AsyncSession,
) -> list[QuestionResponse]:
    row_result = await db.execute(
        select(Assessment, Profile)
        .join(Profile, Assessment.profile_id == Profile.id)
        .where(Assessment.id == assessment_id)
    )
    row = row_result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    assessment, profile = row
    if assessment.profile_id != current_profile_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if block == QuestionBlock.university:
        if profile.age_group != AgeGroup.senior or assessment.goal != AssessmentGoal.university:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Block 'university' is only available for senior age group with goal=university",
            )

    result = await db.execute(
        select(Question)
        .where(Question.block == block, Question.age_group == profile.age_group)
        .order_by(Question.order)
    )
    return [_to_response(q) for q in result.scalars().all()]
