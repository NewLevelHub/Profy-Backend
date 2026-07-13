import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.direction_inquiry import DirectionInquiry
from app.models.direction_roadmap import DirectionRoadmap
from app.models.profile import AgeGroup, Profile
from app.models.question import Question, QuestionBlock
from app.models.user_response import UserResponse
from app.schemas.response import AnswerItem
from app.services import scoring_service

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def _invalidate_direction_flow(
    assessment: Assessment, db: AsyncSession, redis: aioredis.Redis
) -> None:
    """Drop everything derived from the direction flow for this assessment."""
    assessment_id = assessment.id
    slugs_result = await db.execute(
        select(DirectionInquiry.direction_slug).where(
            DirectionInquiry.assessment_id == assessment_id
        )
    )
    slugs = slugs_result.scalars().all()

    await db.execute(
        DirectionRoadmap.__table__.delete().where(
            DirectionRoadmap.assessment_id == assessment_id
        )
    )
    await db.execute(
        DirectionInquiry.__table__.delete().where(
            DirectionInquiry.assessment_id == assessment_id
        )
    )
    assessment.selected_direction_slug = None

    for slug in slugs:
        await redis.delete(f"droadmap:{assessment_id}:{slug}", f"dq:{assessment_id}:{slug}")


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
    # Prefer in-progress; fall back to most recent completed so the frontend
    # can restore state after logout without losing the completed assessment.
    result = await db.execute(
        select(Assessment).where(
            Assessment.profile_id == profile_id,
            Assessment.status == AssessmentStatus.in_progress,
        )
    )
    assessment = result.scalar_one_or_none()
    if assessment is not None:
        return assessment

    result = await db.execute(
        select(Assessment)
        .where(
            Assessment.profile_id == profile_id,
            Assessment.status == AssessmentStatus.completed,
        )
        .order_by(Assessment.created_at.desc())
        .limit(1)
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

    existing_ids_result = await db.execute(
        select(UserResponse.id)
        .join(Question, UserResponse.question_id == Question.id)
        .where(UserResponse.assessment_id == assessment_id, Question.block == block)
    )
    existing_ids = existing_ids_result.scalars().all()
    if existing_ids:
        await db.execute(
            UserResponse.__table__.delete().where(UserResponse.id.in_(existing_ids))
        )
        assessment.status = AssessmentStatus.in_progress
        assessment.completed_at = None

        # Invalidate cached report so retake affects the final result
        old_result = await db.execute(
            select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
        )
        old_analysis = old_result.scalar_one_or_none()
        if old_analysis is not None:
            await db.delete(old_analysis)
        redis = _get_redis()
        await redis.delete(f"report:{assessment_id}")

        # The direction inquiry and its roadmap were derived from the answers that
        # are being replaced — drop them too, and un-confirm the direction.
        await _invalidate_direction_flow(assessment, db, redis)

    question_ids = [item.question_id for item in answers]
    questions_result = await db.execute(
        select(Question).where(Question.id.in_(question_ids))
    )
    questions_map = {q.id: q for q in questions_result.scalars().all()}

    for item in answers:
        question = questions_map.get(item.question_id)
        if question is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Question {item.question_id} not found",
            )
        if scoring_service.is_likert_question(question.options):
            if item.selected_option_index < 0 or item.selected_option_index > 4:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"selected_option_index out of range for question {item.question_id}",
                )
        elif isinstance(question.options, list):
            if item.selected_option_index < 0 or item.selected_option_index >= len(question.options):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"selected_option_index out of range for question {item.question_id}",
                )

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
        .where(
            UserResponse.assessment_id == assessment_id,
            Question.block != QuestionBlock.wellbeing,
        )
    )
    submitted_blocks = submitted_blocks_result.scalar_one() or 0

    # junior skips academic + directions → 5 blocks
    # senior + university goal → 8 blocks
    # all others (middle or senior non-university) → 7 blocks
    if age_group == AgeGroup.junior:
        expected_block_count = 5
    elif assessment.goal == AssessmentGoal.university and age_group == AgeGroup.senior:
        expected_block_count = 8
    else:
        expected_block_count = 7

    assessment.current_block = submitted_blocks
    if submitted_blocks >= expected_block_count:
        assessment.status = AssessmentStatus.completed
        assessment.completed_at = datetime.now(timezone.utc)

    await db.commit()

    return scoring_service.normalize_scores(block_raw_scores)


async def get_raw_scores(assessment_id: uuid.UUID, db: AsyncSession) -> dict[str, Any]:
    """Combined, un-normalized scores across all answers.

    Numeric keys are summed; string keys (preferences) keep their last value.
    Includes signals that normalize_scores drops (pref_*, wb_*, goal_*,
    motivation preferences) so callers can surface them."""
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
    return combined


async def get_total_scores(assessment_id: uuid.UUID, db: AsyncSession) -> dict[str, float]:
    combined = await get_raw_scores(assessment_id, db)
    return scoring_service.normalize_scores(combined)


async def get_wellbeing_raw_scores(
    assessment_id: uuid.UUID, db: AsyncSession
) -> dict[str, float]:
    """Return summed raw scores for wellbeing questions (wb_* keys only)."""
    result = await db.execute(
        select(UserResponse.scores).where(UserResponse.assessment_id == assessment_id)
    )
    combined: dict[str, float] = {}
    for scores in result.scalars().all():
        if not scores:
            continue
        for k, v in scores.items():
            if k.startswith("wb_") and isinstance(v, (int, float)):
                combined[k] = combined.get(k, 0) + v
    return combined
