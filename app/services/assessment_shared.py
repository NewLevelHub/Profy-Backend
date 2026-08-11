"""Low-level helpers shared between assessment_service.py and
motivation_service.py — split out to avoid a circular import (assessment
needs motivation's totals for AssessmentResponse; motivation needs
assessment's Likert totals + retake-invalidation to decide when the whole
test — not just its own phase — is complete)."""

import uuid

import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment
from app.models.direction_inquiry import DirectionInquiry
from app.models.direction_roadmap import DirectionRoadmap
from app.models.profile import AgeGroup, Profile
from app.models.question import Question, QuestionInstrument
from app.models.roadmap import Roadmap
from app.models.user_response import UserResponse
from app.services.age_tiers import visible_tiers

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def invalidate_direction_flow(
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
        DirectionRoadmap.__table__.delete().where(DirectionRoadmap.assessment_id == assessment_id)
    )
    await db.execute(
        DirectionInquiry.__table__.delete().where(DirectionInquiry.assessment_id == assessment_id)
    )
    assessment.selected_direction_slug = None

    for slug in slugs:
        await redis.delete(f"droadmap:{assessment_id}:{slug}", f"dq:{assessment_id}:{slug}")


async def invalidate_goal_roadmap(
    assessment: Assessment, db: AsyncSession, redis: aioredis.Redis
) -> None:
    """Drop the goal roadmap (roadmap_builder.generate_roadmap/get_roadmap):
    the DB row plus every cached variant for this assessment, including the
    program-specific ones from the university gap-analysis path. Cache keys
    are `roadmap:{assessment_id}:{program_hash}` (see roadmap_builder._cache_key)
    — SCAN, not a single known key, because the program_id suffix varies."""
    assessment_id = assessment.id
    pattern = f"roadmap:{assessment_id}:*"
    stale_keys = [key async for key in redis.scan_iter(match=pattern)]
    if stale_keys:
        await redis.delete(*stale_keys)
    await db.execute(Roadmap.__table__.delete().where(Roadmap.assessment_id == assessment_id))


async def invalidate_retake(
    assessment: Assessment, db: AsyncSession, redis: aioredis.Redis
) -> None:
    """Full retake reset, shared by every submit-answers entrypoint (ordinary
    Likert, question pairs, senior motivation triplets, Harter motivation
    pairs): drop the stale report, the direction flow and the goal roadmap so
    a completed retake never leaves old-data artifacts behind for the next
    GET. Caller is still responsible for flipping `assessment.status` back to
    `in_progress` — that's entrypoint-specific (some flip it unconditionally,
    the motivation ones only after checking the other phase)."""
    assessment_id = assessment.id

    old_result = await db.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
    )
    old_analysis = old_result.scalar_one_or_none()
    if old_analysis is not None:
        await db.delete(old_analysis)

    await redis.delete(f"report:{assessment_id}")
    await invalidate_direction_flow(assessment, db, redis)
    await invalidate_goal_roadmap(assessment, db, redis)


async def get_profile_age_group(profile_id: uuid.UUID, db: AsyncSession) -> AgeGroup:
    result = await db.execute(select(Profile.age_group).where(Profile.id == profile_id))
    return result.scalar_one()


async def likert_total_questions(db: AsyncSession, age_group: AgeGroup) -> int:
    query = select(func.count(Question.id)).where(Question.age_tier.in_(visible_tiers(age_group)))
    if age_group == AgeGroup.junior:
        # Junior's RIASEC content is retired in favor of the MI instrument
        # (see question_pair_service.get_pairs) — exclude it from the total
        # so completion tracking doesn't count stale, never-shown questions.
        query = query.where(Question.instrument != QuestionInstrument.riasec)
    result = await db.execute(query)
    return result.scalar_one()


async def likert_answered_count(assessment_id: uuid.UUID, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(UserResponse.id)).where(UserResponse.assessment_id == assessment_id)
    )
    return result.scalar_one()
