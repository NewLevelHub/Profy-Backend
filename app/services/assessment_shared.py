"""Low-level helpers shared between assessment_service.py and
motivation_service.py — split out to avoid a circular import (assessment
needs motivation's totals for AssessmentResponse; motivation needs
assessment's Likert totals + retake-invalidation to decide when the whole
test — not just its own phase — is complete)."""

import logging
import uuid

import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal
from app.models.direction_inquiry import DirectionInquiry
from app.models.direction_roadmap import DirectionRoadmap
from app.models.profile import AgeGroup, Profile
from app.models.question import Question, QuestionInstrument
from app.models.roadmap import Roadmap
from app.models.user_response import UserResponse
from app.services.age_tiers import visible_tiers

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None

# Single source of truth for the report cache key — report_service.py reads/
# writes this, invalidate_retake() below must delete the exact same key.
# Versioned (v2, was bare "report:{id}") so a pre-rollout v1-shaped payload
# can never be read back as v2: the old prefix is simply never addressed
# again by any code path, not filtered out at read time.
REPORT_CACHE_KEY_PREFIX = "report:v2"

# Same versioning principle for the goal roadmap cache — bumped 2026-08-18
# alongside the portrait/recommended_paths prompt rework, so no stale
# pre-rollout cache entry (old wording) can be served after a deploy.
# roadmap_builder._cache_key builds the full key from this prefix; this
# module only needs the prefix to scan-invalidate on retake.
ROADMAP_CACHE_KEY_PREFIX = "roadmap:v2"

# Same principle for the direction roadmap cache — bumped alongside the
# subject_focus-by-grade prompt rework. roadmap_builder.direction_cache_key
# builds the full key from this prefix; this module needs it to delete the
# exact key on invalidate_direction_flow.
DIRECTION_ROADMAP_CACHE_KEY_PREFIX = "droadmap:v2"

# Development plan cache — one key per (assessment_id, program_id).
# development_plan_service._cache_key builds the full key from this prefix;
# invalidate_direction_flow scan-deletes `<prefix>:<assessment_id>:*` on retake.
DEVELOPMENT_PLAN_CACHE_KEY_PREFIX = "devplan:v1"


def report_cache_key(assessment_id: uuid.UUID) -> str:
    return f"{REPORT_CACHE_KEY_PREFIX}:{assessment_id}"


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def safe_redis_delete(redis: aioredis.Redis, *keys: str) -> None:
    """Best-effort cache invalidation: the DB row this cache mirrors is
    deleted/updated in the same transaction by the caller regardless, so a
    Redis outage here means the cache goes stale until its TTL expires —
    not a lost write and not a reason to fail the whole request."""
    if not keys:
        return
    try:
        await redis.delete(*keys)
    except aioredis.RedisError:
        logger.warning("redis delete failed for keys=%s", keys, exc_info=True)


async def safe_redis_scan(redis: aioredis.Redis, pattern: str) -> list[str]:
    try:
        return [key async for key in redis.scan_iter(match=pattern)]
    except aioredis.RedisError:
        logger.warning("redis scan failed for pattern=%s", pattern, exc_info=True)
        return []


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
    from app.models.development_plan import DevelopmentPlan
    await db.execute(
        DevelopmentPlan.__table__.delete().where(DevelopmentPlan.assessment_id == assessment_id)
    )
    assessment.selected_direction_slug = None

    for slug in slugs:
        await safe_redis_delete(
            redis,
            f"{DIRECTION_ROADMAP_CACHE_KEY_PREFIX}:{assessment_id}:{slug}",
            f"dq:{assessment_id}:{slug}",
        )
    # Development plan cache keys are per-program — scan, don't guess program_id.
    stale = await safe_redis_scan(
        redis, f"{DEVELOPMENT_PLAN_CACHE_KEY_PREFIX}:{assessment_id}:*"
    )
    await safe_redis_delete(redis, *stale)


async def invalidate_goal_roadmap(
    assessment_id: uuid.UUID, db: AsyncSession, redis: aioredis.Redis
) -> None:
    """Drop the goal roadmap (roadmap_builder.generate_roadmap/get_roadmap):
    the DB row plus every cached variant for this assessment, including the
    program-specific ones from the university gap-analysis path. Cache keys
    are a plain `roadmap:{assessment_id}:{program_id|"none"}` (see
    roadmap_builder._cache_key — deliberately not hashed) so every variant
    can be found via a scan, not just the one program_id this call happens
    to know about. Takes the bare id (not the `Assessment` object, unlike
    `invalidate_direction_flow`) — see tests/integration/
    test_goal_roadmap_retake_invalidation.py for the contract this matches."""
    pattern = f"{ROADMAP_CACHE_KEY_PREFIX}:{assessment_id}:*"
    stale_keys = await safe_redis_scan(redis, pattern)
    await safe_redis_delete(redis, *stale_keys)
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

    # Reset goal changed count and secondary goals
    assessment.goal_changed_count = 0
    assessment.secondary_goals = []

    # Clean up goal overlays and their caches
    from app.models.goal_overlay import GoalOverlay
    from app.services.goal_overlay_service import invalidate_goal_overlay_cache
    await db.execute(GoalOverlay.__table__.delete().where(GoalOverlay.assessment_id == assessment_id))
    await invalidate_goal_overlay_cache(assessment_id, db)

    await safe_redis_delete(redis, report_cache_key(assessment_id))
    await invalidate_direction_flow(assessment, db, redis)
    await invalidate_goal_roadmap(assessment_id, db, redis)


async def get_profile_age_group(profile_id: uuid.UUID, db: AsyncSession) -> AgeGroup:
    result = await db.execute(select(Profile.age_group).where(Profile.id == profile_id))
    return result.scalar_one()


def get_effective_goal(age_group: AgeGroup, primary_goal: AssessmentGoal) -> AssessmentGoal:
    """The goal actually used to pick a scenario/engine — ТЗ §10.3's soft
    downgrade (middle + "university" -> "profession") applied to the raw
    stored goal. junior always collapses to explore/A regardless of what was
    stored (defensive: the only enforced gate today is at goal-selection and
    goal-change time, not here).

    This is the single source of truth for "which goal does report/roadmap
    generation actually run under" — `goal_overlay_service` uses it to derive
    the displayed scenario (A/B/C) and banner text; `roadmap_builder` and
    `student_context` must use it too so what gets generated always matches
    what the student was told. Never branch on `assessment.goal` directly for
    generation — always resolve it through this function first."""
    if age_group == AgeGroup.junior:
        return AssessmentGoal.explore
    if age_group == AgeGroup.middle and primary_goal == AssessmentGoal.university:
        return AssessmentGoal.profession
    if primary_goal == AssessmentGoal.unsure:
        return AssessmentGoal.explore
    return primary_goal


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
