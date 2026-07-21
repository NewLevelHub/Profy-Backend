import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import assessment_service


async def _make_profile(db: AsyncSession) -> Profile:
    user = User(email=f"{uuid.uuid4()}@test.local", hashed_password="x")
    db.add(user)
    await db.flush()

    profile = Profile(
        user_id=user.id, name="Test Student", age=16, grade=10,
        city="Test City", country="Test Country", language="ru",
        age_group=AgeGroup.senior,
    )
    db.add(profile)
    await db.flush()
    return profile


async def test_create_assessment_abandons_not_completes_a_stale_in_progress_attempt(
    db_session: AsyncSession,
):
    """Starting a new attempt must retire the old unfinished one as `abandoned`,
    not `completed` — nothing was actually finished, so it must not look like
    a done test with a (missing) result."""
    profile = await _make_profile(db_session)
    stale = await assessment_service.create_assessment(profile.id, AssessmentGoal.explore, db_session)

    fresh = await assessment_service.create_assessment(profile.id, AssessmentGoal.explore, db_session)

    await db_session.refresh(stale)
    assert stale.status == AssessmentStatus.abandoned
    assert stale.selected_direction_slug is None
    assert fresh.status == AssessmentStatus.in_progress
    assert fresh.id != stale.id


async def test_get_current_assessment_skips_completed_attempt_with_no_selection(
    db_session: AsyncSession,
):
    """A completed attempt with no selected_direction_slug (disliked result,
    or a pre-`abandoned` leftover) must not shadow an earlier attempt that
    actually has a usable result."""
    profile = await _make_profile(db_session)

    good = await assessment_service.create_assessment(profile.id, AssessmentGoal.explore, db_session)
    good.status = AssessmentStatus.completed
    good.selected_direction_slug = "architect"
    await db_session.commit()

    dead = await assessment_service.create_assessment(profile.id, AssessmentGoal.explore, db_session)
    dead.status = AssessmentStatus.completed
    dead.selected_direction_slug = None
    await db_session.commit()

    current = await assessment_service.get_current_assessment(profile.id, db_session)

    assert current is not None
    assert current.id == good.id
    assert current.selected_direction_slug == "architect"


async def test_get_current_assessment_returns_none_when_nothing_has_a_result(
    db_session: AsyncSession,
):
    profile = await _make_profile(db_session)

    dead = await assessment_service.create_assessment(profile.id, AssessmentGoal.explore, db_session)
    dead.status = AssessmentStatus.completed
    dead.selected_direction_slug = None
    await db_session.commit()

    current = await assessment_service.get_current_assessment(profile.id, db_session)

    assert current is None


async def test_get_current_assessment_prefers_in_progress_over_completed(
    db_session: AsyncSession,
):
    profile = await _make_profile(db_session)

    done = await assessment_service.create_assessment(profile.id, AssessmentGoal.explore, db_session)
    done.status = AssessmentStatus.completed
    done.selected_direction_slug = "architect"
    await db_session.commit()

    resuming = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db_session.add(resuming)
    await db_session.commit()

    current = await assessment_service.get_current_assessment(profile.id, db_session)

    assert current is not None
    assert current.id == resuming.id
