"""Low-level helpers shared between assessment_service.py and
motivation_service.py — split out to avoid a circular import (assessment
needs motivation's totals for AssessmentResponse; motivation needs
assessment's Likert totals + retake-invalidation to decide when the whole
test — not just its own phase — is complete)."""

import logging
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.i18n import DEFAULT_LOCALE, KNOWN_LOCALES
from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.profile import AgeGroup, Profile
from app.models.question import Question, QuestionInstrument
from app.models.user_response import UserResponse
from app.services.age_tiers import visible_tiers

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None

# Single source of truth for the report cache key — report_service.py reads/
# writes this, invalidate_retake() below must delete the exact same key.
# Versioned (was bare "report:{id}", then "report:v2") so a pre-rollout
# payload can never be read back under new semantics: the old prefix is
# simply never addressed again by any code path, not filtered out at read
# time. Bumped to v3 alongside the Big Five relative-tiering / acquiescence
# correction rework — the response shape is unchanged but the personality
# levels a cached v2 payload carries are the old absolute-cutoff ones.
# Bumped to v4 for KZ-405: the key now carries the artifact locale
# (`report:v4:{locale}:{assessment_id}`) so a `ru` and a `kk` report for the
# same assessment don't clobber each other's cache entry.
REPORT_CACHE_KEY_PREFIX = "report:v4"

def report_cache_key(assessment_id: uuid.UUID, locale: str = DEFAULT_LOCALE) -> str:
    return f"{REPORT_CACHE_KEY_PREFIX}:{locale}:{assessment_id}"


def owner_locale_cache_key(assessment_id: uuid.UUID) -> str:
    """Caches the report's owner locale (`users.locale`) so the hot
    `GET /result` path — polled ~every 2s during generation and on every
    results-page load — doesn't run a 2-join `assessment→profile→user` query
    before every cache hit. Invalidated on retake and on `PATCH /auth/me`
    (the only ways the owner locale changes)."""
    return f"{REPORT_CACHE_KEY_PREFIX}:loc:{assessment_id}"


def report_cache_keys(assessment_id: uuid.UUID) -> list[str]:
    """Every per-locale report cache key + the owner-locale pointer — retake /
    invalidation must clear all, not just the one the retaking client is on."""
    return [report_cache_key(assessment_id, loc) for loc in KNOWN_LOCALES] + [
        owner_locale_cache_key(assessment_id)
    ]


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


async def invalidate_retake(
    assessment: Assessment, db: AsyncSession, redis: aioredis.Redis
) -> None:
    """Full retake reset, shared by every submit-answers entrypoint (Likert,
    question pairs, motivation triplets): drop the stale report so a completed
    retake never leaves old-data artifacts behind for the next GET. Caller is still responsible for flipping `assessment.status` back to
    `in_progress` — that's entrypoint-specific (some flip it unconditionally,
    the motivation ones only after checking the other phase)."""
    assessment_id = assessment.id

    # KZ-405: there can be one row per locale — drop them all on retake.
    old_result = await db.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
    )
    for old_analysis in old_result.scalars().all():
        await db.delete(old_analysis)

    # Reset goal changed count and secondary goals
    assessment.goal_changed_count = 0
    assessment.secondary_goals = []

    await safe_redis_delete(redis, *report_cache_keys(assessment_id))


async def get_profile_age_group(profile_id: uuid.UUID, db: AsyncSession) -> AgeGroup:
    result = await db.execute(select(Profile.age_group).where(Profile.id == profile_id))
    return result.scalar_one()


def get_effective_goal(age_group: AgeGroup, primary_goal: AssessmentGoal) -> AssessmentGoal:
    """The goal actually used to pick a scenario/engine — ТЗ §10.3's soft
    downgrade (middle + "university" -> "profession") applied to the raw
    stored goal. junior always collapses to explore/A regardless of what was
    stored (defensive: the only enforced gate today is at goal-selection and
    goal-change time, not here).

    This is the single source of truth for "which goal does report
    generation actually run under" — `goal_overlay_service` uses it to derive
    the displayed scenario (A/B/C) and banner text. Never branch on
    `assessment.goal` directly for generation — always resolve it through
    this function first."""
    if age_group == AgeGroup.junior:
        return AssessmentGoal.explore
    if age_group == AgeGroup.middle and primary_goal == AssessmentGoal.university:
        return AssessmentGoal.profession
    if primary_goal == AssessmentGoal.unsure:
        return AssessmentGoal.explore
    return primary_goal


async def likert_total_questions(db: AsyncSession, age_group: AgeGroup) -> int:
    query = select(func.count(Question.id)).where(
        Question.age_tier.in_(visible_tiers(age_group)),
    )
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


async def motivation_completed(assessment_id: uuid.UUID, age_group: AgeGroup, db: AsyncSession) -> bool:
    """Whether the motivation phase is done, picking the right format by age
    group — senior's MOST/LEAST triplets (motivation_service) vs junior/
    middle's Harter pairs (motivation_pair_service), same branch
    report_service.py uses. Local import for the same circular-import reason
    as try_complete_assessment below (both those modules import this one)."""
    from app.services import motivation_pair_service, motivation_service

    if age_group == AgeGroup.senior:
        mot_answered = await motivation_service.answered_count(assessment_id, db)
        mot_total = await motivation_service.total_triplets(db)
    else:
        mot_answered = await motivation_pair_service.answered_count(assessment_id, db)
        mot_total = await motivation_pair_service.total_pairs(db)
    return mot_total > 0 and mot_answered >= mot_total


async def belbin_and_astur_completed(assessment_id: uuid.UUID, db: AsyncSession) -> bool:
    """Whether both Belbin and АСТУР are done for this assessment. Belbin/
    АСТУР used to be treated as separate/optional (an older comment
    elsewhere in this codebase claimed they're psychologist-only), but the
    continuous flow (MotivationTripletFlow.tsx / MotivationHarterFlow.tsx)
    routes every student through both right after motivation — so anything
    that decides "is this assessment actually done" (report generation,
    `assessment.status`) must require them too, or a student who exits
    between motivation and Belbin gets a "report ready" screen for a test
    they haven't finished (observed live: an assessment marked completed
    with 0 belbin_runs and 0 astur_runs).

    Local import: belbin_service/astur_service are import-free of this
    module, so this direction is safe, but keeping it local (rather than at
    module level) keeps this file's own import graph simple regardless."""
    from app.services import astur_service, belbin_service

    belbin_run = await belbin_service.get_latest_run(assessment_id, db)
    if belbin_run is None:
        return False
    astur_run = await astur_service.get_latest_run(assessment_id, db)
    return astur_run is not None and astur_service.is_complete(astur_run)


async def try_complete_assessment(
    assessment: Assessment, *, likert_completed: bool, motivation_completed: bool, db: AsyncSession
) -> bool:
    """Flips `assessment.status` to `completed` once every required phase is
    actually done — Likert/pairs, motivation, Belbin, AND АСТУР (see
    `belbin_and_astur_completed`). Called from the tail end of each phase's
    own submit (motivation_service, motivation_pair_service, astur router)
    since none of them alone knows when the *last* phase finishes; whichever
    call lands last is the one that actually flips it.

    Does not commit — caller's existing commit picks this up in the same
    transaction as its own phase's write, so a completed-without-Belbin/
    АСТУР assessment can't land even under a partial failure."""
    if assessment.status == AssessmentStatus.completed:
        return False
    if not (likert_completed and motivation_completed):
        return False
    if not await belbin_and_astur_completed(assessment.id, db):
        return False

    assessment.status = AssessmentStatus.completed
    assessment.completed_at = datetime.now(timezone.utc)
    return True


async def response_time_deltas_ms(
    assessment_id: uuid.UUID, db: AsyncSession
) -> list[int]:
    """Passively-collected reaction-time signal for the protocol-validity
    module (PRO-298): milliseconds between consecutive answer saves, in save
    order. Read straight off `user_responses.created_at` (stamped server-side
    on every write) — nothing is collected from or shown to the client.

    NOT part of scoring. validity_service (PRO-299) stores this on
    `assessment_validity.rt_ms` as raw calibration data only; `sd_level` /
    `traffic_light` never depend on it.

    Granularity is page-level, not per-question: the client submits answers
    in batches (LikertPage = 5 at a time) and each batch is one INSERT, so
    every row in a batch shares a `created_at` and appears here as a run of
    `0`s followed by one real inter-batch gap ≈ time spent on that page. The
    ticket forbids a frontend change, so finer timing isn't available.
    """
    result = await db.execute(
        select(UserResponse.created_at)
        .where(UserResponse.assessment_id == assessment_id)
        .order_by(UserResponse.created_at, UserResponse.id)
    )
    stamps = list(result.scalars().all())
    return [
        max(0, round((later - earlier).total_seconds() * 1000))
        for earlier, later in zip(stamps, stamps[1:])
    ]
