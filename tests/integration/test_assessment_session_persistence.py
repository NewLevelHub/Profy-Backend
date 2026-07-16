import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.assessment_session import AssessmentSession
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services.assessment_session_service import get_or_create_session, save_session


async def _make_assessment(db: AsyncSession) -> Assessment:
    user = User(email=f"{uuid.uuid4()}@test.local", hashed_password="x")
    db.add(user)
    await db.flush()

    profile = Profile(
        user_id=user.id,
        name="Test Student",
        age=15,
        grade=9,
        city="Test City",
        country="Test Country",
        language="ru",
        age_group=AgeGroup.senior,
    )
    db.add(profile)
    await db.flush()

    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()

    return assessment


async def test_round_trip_belief_survives_save_and_reread(db_session: AsyncSession):
    assessment = await _make_assessment(db_session)

    session = await get_or_create_session(assessment.id, db_session)
    assert session.belief == {}

    await save_session(
        session,
        db_session,
        belief={"teacher": 0.6, "engineer": 0.4},
        asked_question_ids=["q1"],
        asked_axis_families=["A"],
        step=1,
    )

    reread = await get_or_create_session(assessment.id, db_session)
    assert reread.id == session.id
    assert reread.belief == {"teacher": 0.6, "engineer": 0.4}
    assert reread.asked_question_ids == ["q1"]
    assert reread.asked_axis_families == ["A"]
    assert reread.step == 1


async def test_get_or_create_is_idempotent(db_session: AsyncSession):
    assessment = await _make_assessment(db_session)

    first = await get_or_create_session(assessment.id, db_session)
    second = await get_or_create_session(assessment.id, db_session)
    assert first.id == second.id


async def test_unique_constraint_allows_at_most_one_session_per_assessment(
    db_session: AsyncSession,
):
    assessment = await _make_assessment(db_session)

    db_session.add(AssessmentSession(assessment_id=assessment.id))
    await db_session.commit()

    db_session.add(AssessmentSession(assessment_id=assessment.id))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_belief_not_summing_to_one_is_rejected(db_session: AsyncSession):
    assessment = await _make_assessment(db_session)
    session = await get_or_create_session(assessment.id, db_session)

    with pytest.raises(ValueError):
        await save_session(session, db_session, belief={"teacher": 0.9, "engineer": 0.5})
