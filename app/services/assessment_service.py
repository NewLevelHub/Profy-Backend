import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.direction_inquiry import DirectionInquiry
from app.models.direction_roadmap import DirectionRoadmap
from app.models.profile import Profile
from app.models.question import Question
from app.models.user_response import UserResponse
from app.schemas.assessment import AssessmentResponse
from app.schemas.response import AnswerItem, SubmitAnswersResponse
from app.services import riasec_service

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


async def _total_questions(db: AsyncSession) -> int:
    result = await db.execute(select(func.count(Question.id)))
    return result.scalar_one()


async def _answered_count(assessment_id: uuid.UUID, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(UserResponse.id)).where(UserResponse.assessment_id == assessment_id)
    )
    return result.scalar_one()


async def _to_response(assessment: Assessment, db: AsyncSession) -> AssessmentResponse:
    answered = await _answered_count(assessment.id, db)
    total = await _total_questions(db)
    return AssessmentResponse(
        id=assessment.id,
        goal=assessment.goal,
        status=assessment.status,
        answered_count=answered,
        total_questions=total,
        created_at=assessment.created_at,
    )


async def create_assessment(
    profile_id: uuid.UUID, goal: AssessmentGoal, db: AsyncSession
) -> AssessmentResponse:
    profile_result = await db.execute(select(Profile).where(Profile.id == profile_id))
    profile = profile_result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

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
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)
    return await _to_response(assessment, db)


async def get_current_assessment(profile_id: uuid.UUID, db: AsyncSession) -> AssessmentResponse | None:
    # Prefer in-progress; fall back to most recent completed so the frontend
    # can restore state after logout without losing the completed assessment.
    result = await db.execute(
        select(Assessment).where(
            Assessment.profile_id == profile_id,
            Assessment.status == AssessmentStatus.in_progress,
        )
    )
    assessment = result.scalar_one_or_none()
    if assessment is None:
        result = await db.execute(
            select(Assessment)
            .where(
                Assessment.profile_id == profile_id,
                Assessment.status == AssessmentStatus.completed,
            )
            .order_by(Assessment.created_at.desc())
            .limit(1)
        )
        assessment = result.scalar_one_or_none()

    if assessment is None:
        return None
    return await _to_response(assessment, db)


async def submit_answers(
    assessment_id: uuid.UUID,
    answers: list[AnswerItem],
    current_profile_id: uuid.UUID,
    db: AsyncSession,
) -> SubmitAnswersResponse:
    row_result = await db.execute(select(Assessment).where(Assessment.id == assessment_id))
    assessment = row_result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    if assessment.profile_id != current_profile_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    question_ids = [item.question_id for item in answers]
    questions_result = await db.execute(select(Question.id).where(Question.id.in_(question_ids)))
    valid_ids = set(questions_result.scalars().all())
    for item in answers:
        if item.question_id not in valid_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Question {item.question_id} not found",
            )

    is_retake = assessment.status == AssessmentStatus.completed
    if answers:
        stmt = pg_insert(UserResponse).values([
            {
                "id": uuid.uuid4(),
                "assessment_id": assessment_id,
                "question_id": item.question_id,
                "answer_value": item.value,
            }
            for item in answers
        ])
        stmt = stmt.on_conflict_do_update(
            constraint="uq_user_response_assessment_question",
            set_={"answer_value": stmt.excluded.answer_value},
        )
        await db.execute(stmt)

    if is_retake:
        assessment.status = AssessmentStatus.in_progress
        assessment.completed_at = None

        old_result = await db.execute(
            select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
        )
        old_analysis = old_result.scalar_one_or_none()
        if old_analysis is not None:
            await db.delete(old_analysis)
        redis = _get_redis()
        await redis.delete(f"report:{assessment_id}")
        await _invalidate_direction_flow(assessment, db, redis)

    answered = await _answered_count(assessment_id, db)
    total = await _total_questions(db)
    completed = total > 0 and answered >= total

    if completed and assessment.status != AssessmentStatus.completed:
        assessment.status = AssessmentStatus.completed
        assessment.completed_at = datetime.now(timezone.utc)

    await db.commit()

    return SubmitAnswersResponse(answered_count=answered, total=total, completed=completed)


async def get_raw_scores(assessment_id: uuid.UUID, db: AsyncSession) -> dict[str, int]:
    return await riasec_service.raw_scores(assessment_id, db)


async def get_total_scores(assessment_id: uuid.UUID, db: AsyncSession) -> dict[str, float]:
    raw = await riasec_service.raw_scores(assessment_id, db)
    counts = await riasec_service.question_counts(db)
    return riasec_service.normalize(raw, counts)
