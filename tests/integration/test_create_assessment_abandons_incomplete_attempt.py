"""Live bug found via a user support request (test@testmail.com): starting
a new assessment while a previous `in_progress` one was genuinely
incomplete (e.g. Likert answered, Harter motivation pairs never touched)
used to stamp the old one as `AssessmentStatus.completed` — a lie every
other consumer of that status trusts (`_assert_assessment_complete`,
`/result/generate`, `get_current_assessment`'s fallback query). The
abandoned attempt was then permanently stuck: `status=completed` but no
`AnalysisResult` could ever be built for it, since the real completion
check correctly rejected it — `/result` 409'd on generate and 404'd on GET.

Fix: `create_assessment()` now deletes an abandoned incomplete `in_progress`
assessment instead of relabeling it — matching the "discard stale
artifacts on a fresh start" pattern retake invalidation already uses
elsewhere (assessment_shared.invalidate_retake).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.profile import AgeGroup, Profile
from app.models.question import BigFiveDomain, Question, QuestionInstrument
from app.models.user import User
from app.models.user_response import UserResponse
from app.services import assessment_service


async def _make_profile(db: AsyncSession) -> Profile:
    user = User(
        email=f"{uuid.uuid4()}@example.test", hashed_password="x", is_active=True, is_verified=True,
    )
    db.add(user)
    await db.flush()
    profile = Profile(
        user_id=user.id, name="Тест", age=12, grade=6,
        city="Алматы", country="Казахстан", language="ru", age_group=AgeGroup.middle,
    )
    db.add(profile)
    await db.flush()
    return profile


async def test_abandoned_incomplete_in_progress_assessment_is_deleted_not_relabeled(
    db_session: AsyncSession,
) -> None:
    profile = await _make_profile(db_session)
    abandoned = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore, status=AssessmentStatus.in_progress)
    db_session.add(abandoned)
    await db_session.flush()

    # Some real progress on the abandoned attempt — answered Likert, never
    # touched motivation. This is exactly the shape that used to get stuck.
    question = Question(
        instrument=QuestionInstrument.big_five, bigfive_domain=BigFiveDomain.O,
        text="test-q", age_tier=AgeGroup.middle,
    )
    db_session.add(question)
    await db_session.flush()
    db_session.add(UserResponse(assessment_id=abandoned.id, question_id=question.id, answer_value=4))
    await db_session.flush()
    abandoned_id = abandoned.id

    await assessment_service.create_assessment(profile.id, AssessmentGoal.profession, db_session)

    stale = (
        await db_session.execute(select(Assessment).where(Assessment.id == abandoned_id))
    ).scalar_one_or_none()
    assert stale is None, "the abandoned incomplete assessment must be deleted, not stamped completed"

    orphaned_responses = (
        await db_session.execute(select(UserResponse).where(UserResponse.assessment_id == abandoned_id))
    ).scalars().all()
    assert orphaned_responses == [], "its UserResponse rows must be gone too (cascade), not orphaned"


async def test_new_assessment_after_abandoning_one_is_in_progress(db_session: AsyncSession) -> None:
    profile = await _make_profile(db_session)
    old = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore, status=AssessmentStatus.in_progress)
    db_session.add(old)
    await db_session.flush()

    response = await assessment_service.create_assessment(profile.id, AssessmentGoal.profession, db_session)

    assert response.status == AssessmentStatus.in_progress
    assert response.goal == AssessmentGoal.profession

    all_assessments = (
        await db_session.execute(select(Assessment).where(Assessment.profile_id == profile.id))
    ).scalars().all()
    assert len(all_assessments) == 1, "only the new assessment should remain"
