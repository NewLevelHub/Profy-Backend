"""PRO-298: `rt_ms` is passively collected — inter-answer Δt read straight
off `user_responses.created_at`, page-level granularity, never negative,
not wired into scoring (that's PRO-299's `assessment_validity.rt_ms`)."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.question import Question, QuestionInstrument
from app.models.user import User
from app.models.user_response import UserResponse
from app.services import assessment_shared

_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


async def _assessment(db: AsyncSession) -> Assessment:
    user = User(
        email=f"{uuid.uuid4()}@example.com", hashed_password="x",
        is_active=True, is_verified=True,
    )
    db.add(user)
    await db.flush()
    profile = Profile(
        user_id=user.id, name="Т", age=16, grade=10, city="Алматы",
        country="Казахстан", language="ru", age_group=AgeGroup.senior,
    )
    db.add(profile)
    await db.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()
    return assessment


async def _questions(db: AsyncSession, n: int) -> list[Question]:
    qs = [
        Question(
            instrument=QuestionInstrument.big_five, text=f"q{i}",
            order=i, age_tier=AgeGroup.senior,
        )
        for i in range(n)
    ]
    db.add_all(qs)
    await db.flush()
    return qs


async def test_deltas_are_ms_between_consecutive_saves_in_order(
    db_session: AsyncSession,
) -> None:
    assessment = await _assessment(db_session)
    qs = await _questions(db_session, 4)

    # a batch of 2 saved together, then one page 3 s later, one 0.5 s after that
    for q, ms in zip(qs, [0, 0, 3000, 3500]):
        db_session.add(UserResponse(
            assessment_id=assessment.id, question_id=q.id, answer_value=4,
            created_at=_T0 + timedelta(milliseconds=ms),
        ))
    await db_session.flush()

    deltas = await assessment_shared.response_time_deltas_ms(assessment.id, db_session)
    assert deltas == [0, 3000, 500]


async def test_no_responses_returns_empty(db_session: AsyncSession) -> None:
    assessment = await _assessment(db_session)
    assert await assessment_shared.response_time_deltas_ms(assessment.id, db_session) == []


async def test_deltas_never_negative_when_stamps_are_equal(
    db_session: AsyncSession,
) -> None:
    assessment = await _assessment(db_session)
    qs = await _questions(db_session, 3)
    for q in qs:
        db_session.add(UserResponse(
            assessment_id=assessment.id, question_id=q.id, answer_value=3, created_at=_T0,
        ))
    await db_session.flush()

    assert await assessment_shared.response_time_deltas_ms(assessment.id, db_session) == [0, 0]


async def test_deltas_scoped_to_one_assessment(db_session: AsyncSession) -> None:
    a1 = await _assessment(db_session)
    a2 = await _assessment(db_session)
    qs = await _questions(db_session, 4)

    db_session.add(UserResponse(
        assessment_id=a1.id, question_id=qs[0].id, answer_value=4, created_at=_T0,
    ))
    db_session.add(UserResponse(
        assessment_id=a1.id, question_id=qs[1].id, answer_value=4,
        created_at=_T0 + timedelta(seconds=2),
    ))
    db_session.add(UserResponse(
        assessment_id=a2.id, question_id=qs[2].id, answer_value=4,
        created_at=_T0 + timedelta(seconds=99),
    ))
    await db_session.flush()

    assert await assessment_shared.response_time_deltas_ms(a1.id, db_session) == [2000]
    assert await assessment_shared.response_time_deltas_ms(a2.id, db_session) == []
