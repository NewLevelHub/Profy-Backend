import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.profile import AgeGroup, Profile
from app.models.question import Question, QuestionBlock
from app.models.user_response import UserResponse
from app.schemas.response import AnswerItem
from app.services import scoring_service


async def create_assessment(
    profile_id: uuid.UUID, goal: AssessmentGoal, db: AsyncSession
) -> Assessment:
    profile_result = await db.execute(select(Profile).where(Profile.id == profile_id))
    profile = profile_result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    if goal == AssessmentGoal.university and profile.age_group != AgeGroup.senior:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Goal 'university' is only available for senior age group",
        )

    existing_result = await db.execute(
        select(Assessment).where(
            Assessment.profile_id == profile_id,
            Assessment.status == AssessmentStatus.in_progress,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        existing.status = AssessmentStatus.completed
        await db.commit()

    assessment = Assessment(
        profile_id=profile_id,
        goal=goal,
        status=AssessmentStatus.in_progress,
        current_block=0,
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)
    return assessment


async def get_current_assessment(profile_id: uuid.UUID, db: AsyncSession) -> Assessment | None:
    result = await db.execute(
        select(Assessment).where(
            Assessment.profile_id == profile_id,
            Assessment.status == AssessmentStatus.in_progress,
        )
    )
    return result.scalar_one_or_none()


async def complete_block(
    assessment_id: uuid.UUID,
    block: QuestionBlock,
    answers: list[AnswerItem],
    current_profile_id: uuid.UUID,
    db: AsyncSession,
) -> dict[str, float]:
    row_result = await db.execute(
        select(Assessment, Profile.age_group)
        .join(Profile, Assessment.profile_id == Profile.id)
        .where(Assessment.id == assessment_id)
    )
    row = row_result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    assessment, age_group = row

    if assessment.profile_id != current_profile_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if assessment.status == AssessmentStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assessment already completed",
        )

    existing_result = await db.execute(
        select(UserResponse.id)
        .join(Question, UserResponse.question_id == Question.id)
        .where(UserResponse.assessment_id == assessment_id, Question.block == block)
        .limit(1)
    )
    if existing_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Answers for this block were already submitted",
        )

    question_ids = [item.question_id for item in answers]
    questions_result = await db.execute(
        select(Question).where(Question.id.in_(question_ids))
    )
    questions_map = {q.id: q for q in questions_result.scalars().all()}

    block_raw_scores = scoring_service.calculate_scores(questions_map, answers)

    records = [
        UserResponse(
            assessment_id=assessment_id,
            question_id=item.question_id,
            selected_option_index=item.selected_option_index,
            scores=scoring_service.get_answer_scores(
                questions_map[item.question_id], item.selected_option_index
            ) if item.question_id in questions_map else {},
        )
        for item in answers
    ]
    db.add_all(records)
    await db.flush()

    submitted_blocks_result = await db.execute(
        select(func.count(func.distinct(Question.block)))
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(UserResponse.assessment_id == assessment_id)
    )
    submitted_count = submitted_blocks_result.scalar_one() or 0

    expected_blocks_result = await db.execute(
        select(func.count(func.distinct(Question.block)))
        .where(Question.age_group == age_group)
    )
    expected_count = expected_blocks_result.scalar_one() or 0

    assessment.current_block = submitted_count
    if expected_count > 0 and submitted_count >= expected_count:
        assessment.status = AssessmentStatus.completed
        assessment.completed_at = datetime.now(timezone.utc)

    await db.commit()

    return scoring_service.normalize_scores(block_raw_scores)


async def get_total_scores(assessment_id: uuid.UUID, db: AsyncSession) -> dict[str, float]:
    result = await db.execute(
        select(UserResponse.scores).where(UserResponse.assessment_id == assessment_id)
    )
    all_scores: list[dict[str, Any]] = result.scalars().all()

    combined: dict[str, Any] = {}
    for scores in all_scores:
        if not scores:
            continue
        for k, v in scores.items():
            if isinstance(v, (int, float)):
                combined[k] = combined.get(k, 0) + v
            elif isinstance(v, str):
                combined[k] = v

    return scoring_service.normalize_scores(combined)
