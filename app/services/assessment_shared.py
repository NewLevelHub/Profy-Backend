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
from app.models.assessment import Assessment
from app.models.direction_inquiry import DirectionInquiry
from app.models.direction_roadmap import DirectionRoadmap
from app.models.profile import AgeGroup, Profile
from app.models.question import Question
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


async def get_profile_age_group(profile_id: uuid.UUID, db: AsyncSession) -> AgeGroup:
    result = await db.execute(select(Profile.age_group).where(Profile.id == profile_id))
    return result.scalar_one()


async def likert_total_questions(db: AsyncSession, age_group: AgeGroup) -> int:
    result = await db.execute(
        select(func.count(Question.id)).where(Question.age_tier.in_(visible_tiers(age_group)))
    )
    return result.scalar_one()


async def likert_answered_count(assessment_id: uuid.UUID, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(UserResponse.id)).where(UserResponse.assessment_id == assessment_id)
    )
    return result.scalar_one()
