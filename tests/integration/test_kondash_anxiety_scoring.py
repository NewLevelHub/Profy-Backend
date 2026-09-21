"""PRO-338 Ф1.11 — raw-score reads against real seeded kondash_anxiety
content, scoped to the межличностная (interpersonal) subscale only, the
one this ticket's "Соц. уверенность" half actually uses."""
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.question import Question, QuestionInstrument
from app.models.user import User
from app.models.user_response import UserResponse
from app.services import kondash_anxiety_service
from scripts.kondash_anxiety_bank import QUESTIONS


async def _seed_bank(db: AsyncSession) -> None:
    await db.execute(delete(Question).where(Question.instrument == QuestionInstrument.kondash_anxiety))
    for q in QUESTIONS:
        db.add(Question(
            instrument=QuestionInstrument.kondash_anxiety,
            text=q["text"], order=q["order"], age_tier=AgeGroup.senior,
        ))
    await db.flush()


async def _make_assessment(db: AsyncSession) -> Assessment:
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x", is_active=True, is_verified=True)
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


async def test_interpersonal_raw_score_none_when_nothing_answered(db_session: AsyncSession) -> None:
    await _seed_bank(db_session)
    assessment = await _make_assessment(db_session)
    assert await kondash_anxiety_service.interpersonal_raw_score(assessment.id, db_session) is None


async def test_interpersonal_raw_score_sums_only_the_interpersonal_subscale(db_session: AsyncSession) -> None:
    await _seed_bank(db_session)
    assessment = await _make_assessment(db_session)

    # item 2 (order 548) = interpersonal -> answer 3
    # item 9 (order 555) = interpersonal -> answer 4
    # item 1 (order 547) = school (NOT interpersonal) -> answer 4, must be excluded
    by_order = {q.order: q for q in (await db_session.execute(
        select(Question).where(Question.instrument == QuestionInstrument.kondash_anxiety)
    )).scalars().all()}

    db_session.add(UserResponse(assessment_id=assessment.id, question_id=by_order[548].id, answer_value=3))
    db_session.add(UserResponse(assessment_id=assessment.id, question_id=by_order[555].id, answer_value=4))
    db_session.add(UserResponse(assessment_id=assessment.id, question_id=by_order[547].id, answer_value=4))
    await db_session.flush()

    score = await kondash_anxiety_service.interpersonal_raw_score(assessment.id, db_session)

    assert score == 7
