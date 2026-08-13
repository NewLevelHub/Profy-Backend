"""Retake must not leave a stale goal roadmap behind.

Bug: `invalidate_direction_flow` (called on retake) only ever cleared the
direction roadmap — the goal roadmap (`roadmaps` table + its Redis cache)
survived a retake untouched, and `roadmap_builder.generate_roadmap` checks
its Redis cache *before* touching the DB, so a stale plan could outlive the
test it was generated from for up to CACHE_TTL (24h). Fixed by
`assessment_shared.invalidate_goal_roadmap`, called from both retake sites
(`assessment_service.submit_answers`, `motivation_service.
submit_motivation_answers`) alongside the existing `invalidate_direction_flow`.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.roadmap import Roadmap
from app.models.user import User
from app.services import assessment_shared


async def _make_assessment(db: AsyncSession) -> Assessment:
    user = User(email=f"{uuid.uuid4()}@test.local", hashed_password="x")
    db.add(user)
    await db.flush()

    profile = Profile(
        user_id=user.id, name="Test Student", age=16, grade=10,
        city="Алматы", country="Казахстан", language="ru", age_group=AgeGroup.senior,
    )
    db.add(profile)
    await db.flush()

    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()
    return assessment


async def test_invalidate_goal_roadmap_deletes_the_row(db_session: AsyncSession):
    assessment = await _make_assessment(db_session)
    db_session.add(Roadmap(assessment_id=assessment.id, goal="explore", milestones=[]))
    await db_session.flush()

    redis = assessment_shared.get_redis()
    await assessment_shared.invalidate_goal_roadmap(assessment.id, db_session, redis)

    row = (
        await db_session.execute(select(Roadmap).where(Roadmap.assessment_id == assessment.id))
    ).scalar_one_or_none()
    assert row is None


async def test_invalidate_goal_roadmap_clears_every_cached_program_id_variant(
    db_session: AsyncSession,
):
    """One assessment can have several cached variants — one per distinct
    program_id ever passed to POST /roadmap/generate for the university
    gap-analysis case. All of them must go, not just the no-program_id one."""
    assessment = await _make_assessment(db_session)
    redis = assessment_shared.get_redis()

    no_program_key = f"roadmap:{assessment.id}:none"
    program_a_key = f"roadmap:{assessment.id}:{uuid.uuid4()}"
    program_b_key = f"roadmap:{assessment.id}:{uuid.uuid4()}"
    other_assessment_key = f"roadmap:{uuid.uuid4()}:none"

    for key in (no_program_key, program_a_key, program_b_key, other_assessment_key):
        await redis.set(key, "{}")

    try:
        await assessment_shared.invalidate_goal_roadmap(assessment.id, db_session, redis)

        assert await redis.get(no_program_key) is None
        assert await redis.get(program_a_key) is None
        assert await redis.get(program_b_key) is None
        # A different assessment's cache entry must survive — this isn't a
        # blanket flush, it's scoped to this assessment_id's own keys.
        assert await redis.get(other_assessment_key) == "{}"
    finally:
        await redis.delete(other_assessment_key)


async def test_cache_key_is_plain_and_scannable():
    """Guards the precondition invalidate_goal_roadmap relies on: the cache
    key must be a readable `roadmap:{assessment_id}:{program_id}` — a hash
    would make it impossible to find all of an assessment's cached variants
    without already knowing every program_id ever used."""
    from app.services.roadmap_builder import _cache_key

    assessment_id = uuid.uuid4()
    program_id = uuid.uuid4()

    assert _cache_key(assessment_id, None) == f"roadmap:{assessment_id}:none"
    assert _cache_key(assessment_id, program_id) == f"roadmap:{assessment_id}:{program_id}"
