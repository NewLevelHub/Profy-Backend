"""PRO-338 Ф1.5 — raw-score reads against real seeded eysenck content."""
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.question import Question, QuestionInstrument
from app.models.user import User
from app.models.user_response import UserResponse
from app.services import eysenck_service
from scripts.eysenck_bank import QUESTIONS

_YES = 2
_NO = 1


async def _seed_bank(db: AsyncSession) -> None:
    await db.execute(delete(Question).where(Question.instrument == QuestionInstrument.eysenck))
    for q in QUESTIONS:
        db.add(Question(
            instrument=QuestionInstrument.eysenck,
            text=q["text"], order=q["order"],
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


async def test_raw_scores_none_when_nothing_answered(db_session: AsyncSession) -> None:
    await _seed_bank(db_session)
    assessment = await _make_assessment(db_session)
    assert await eysenck_service.raw_scores(assessment.id, db_session) is None


async def test_raw_scores_counts_only_key_matching_answers(db_session: AsyncSession) -> None:
    await _seed_bank(db_session)
    assessment = await _make_assessment(db_session)

    # item 1 (order 410) = extraversion, keyed "yes" -> answer Да (2) scores
    # item 5 (order 414) = extraversion, keyed "no" -> answer Да (2) does NOT score
    # item 2 (order 411) = neuroticism, keyed "yes" -> answer Нет (1) does NOT score
    # item 6 (order 415) = lie, keyed "yes" -> answer Да (2) scores
    by_order = {q.order: q for q in (await db_session.execute(
        select(Question).where(Question.instrument == QuestionInstrument.eysenck)
    )).scalars().all()}

    db_session.add(UserResponse(assessment_id=assessment.id, question_id=by_order[410].id, answer_value=_YES))
    db_session.add(UserResponse(assessment_id=assessment.id, question_id=by_order[414].id, answer_value=_YES))
    db_session.add(UserResponse(assessment_id=assessment.id, question_id=by_order[411].id, answer_value=_NO))
    db_session.add(UserResponse(assessment_id=assessment.id, question_id=by_order[415].id, answer_value=_YES))
    await db_session.flush()

    scores = await eysenck_service.raw_scores(assessment.id, db_session)

    assert scores == {"extraversion": 1, "neuroticism": 0, "lie": 1}
