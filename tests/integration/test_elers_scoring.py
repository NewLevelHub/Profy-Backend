"""PRO-338 Ф1.8 — raw-score reads against real seeded elers content."""
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.question import Question, QuestionInstrument
from app.models.user import User
from app.models.user_response import UserResponse
from app.services import elers_service
from scripts.elers_bank import QUESTIONS

_YES = 2
_NO = 1


async def _seed_bank(db: AsyncSession) -> None:
    await db.execute(delete(Question).where(Question.instrument == QuestionInstrument.elers))
    for q in QUESTIONS:
        db.add(Question(
            instrument=QuestionInstrument.elers,
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


async def test_raw_score_none_when_nothing_answered(db_session: AsyncSession) -> None:
    await _seed_bank(db_session)
    assessment = await _make_assessment(db_session)
    assert await elers_service.raw_score(assessment.id, db_session) is None


async def test_raw_score_excludes_buffer_and_counts_only_key_matches(db_session: AsyncSession) -> None:
    await _seed_bank(db_session)
    assessment = await _make_assessment(db_session)

    # item 1 (order 470) = buffer -> never scores, whatever the answer
    # item 2 (order 471) = keyed "yes" -> answer Да (2) scores
    # item 3 (order 472) = keyed "yes" -> answer Нет (1) does NOT score
    # item 6 (order 475) = keyed "no"  -> answer Нет (1) scores
    by_order = {q.order: q for q in (await db_session.execute(
        select(Question).where(Question.instrument == QuestionInstrument.elers)
    )).scalars().all()}

    db_session.add(UserResponse(assessment_id=assessment.id, question_id=by_order[470].id, answer_value=_YES))
    db_session.add(UserResponse(assessment_id=assessment.id, question_id=by_order[471].id, answer_value=_YES))
    db_session.add(UserResponse(assessment_id=assessment.id, question_id=by_order[472].id, answer_value=_NO))
    db_session.add(UserResponse(assessment_id=assessment.id, question_id=by_order[475].id, answer_value=_NO))
    await db_session.flush()

    score = await elers_service.raw_score(assessment.id, db_session)

    assert score == 2
