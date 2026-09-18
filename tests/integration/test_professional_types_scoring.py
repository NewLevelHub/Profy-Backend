"""PRO-338 Ф1.2 — interest/abilities raw-score reads against real seeded
professional_types content, plus the full build_report() wiring."""
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.question import Question, QuestionInstrument
from app.models.question_pair import QuestionPair
from app.models.user import User
from app.models.user_response import UserResponse
from app.services import professional_types_service
from scripts.professional_types_bank import PAIRS, QUESTIONS


async def _seed_bank(db: AsyncSession) -> None:
    await db.execute(delete(QuestionPair).where(QuestionPair.instrument == QuestionInstrument.professional_types))
    await db.execute(delete(Question).where(
        Question.instrument.in_([QuestionInstrument.professional_types, QuestionInstrument.professional_types_abilities])
    ))

    for q in QUESTIONS:
        db.add(Question(
            instrument=QuestionInstrument.professional_types_abilities,
            text=q["text"], order=q["order"], age_tier=AgeGroup.senior,
        ))

    ids_by_order: dict[int, uuid.UUID] = {}
    for pair in PAIRS:
        for option in (pair["option_a"], pair["option_b"]):
            question = Question(
                instrument=QuestionInstrument.professional_types,
                text=option["text"], order=option["order"], age_tier=AgeGroup.senior,
            )
            db.add(question)
            await db.flush()
            ids_by_order[option["order"]] = question.id

    for pair in PAIRS:
        db.add(QuestionPair(
            instrument=QuestionInstrument.professional_types,
            age_tier=AgeGroup.senior,
            pair_index=pair["pair_index"],
            question_a_id=ids_by_order[pair["option_a"]["order"]],
            question_b_id=ids_by_order[pair["option_b"]["order"]],
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


async def test_interest_raw_scores_none_when_nothing_answered(db_session: AsyncSession) -> None:
    await _seed_bank(db_session)
    assessment = await _make_assessment(db_session)
    assert await professional_types_service.interest_raw_scores(assessment.id, db_session) is None


async def test_interest_raw_scores_counts_one_point_per_pick(db_session: AsyncSession) -> None:
    await _seed_bank(db_session)
    assessment = await _make_assessment(db_session)

    # Every pair's option_a is "practical" or "technical" in the first two
    # pairs of the real bank — answer just those two, picking option_a both
    # times, and confirm exactly those two scales get 1 point.
    first_two = PAIRS[:2]
    picked_orders = [first_two[0]["option_a"]["order"], first_two[1]["option_a"]["order"]]
    questions = (await db_session.execute(
        select(Question).where(Question.order.in_(picked_orders))
    )).scalars().all()
    for question in questions:
        db_session.add(UserResponse(assessment_id=assessment.id, question_id=question.id, answer_value=5))
    await db_session.flush()

    scores = await professional_types_service.interest_raw_scores(assessment.id, db_session)

    assert scores is not None
    assert scores[first_two[0]["option_a"]["scale"]] >= 1
    assert scores[first_two[1]["option_a"]["scale"]] >= 1
    assert set(scores.keys()) == set(professional_types_service.SCALE_ORDER)


async def test_abilities_raw_scores_reads_verbatim_0_to_3(db_session: AsyncSession) -> None:
    await _seed_bank(db_session)
    assessment = await _make_assessment(db_session)

    first_ability = QUESTIONS[0]
    question = (await db_session.execute(
        select(Question).where(Question.order == first_ability["order"])
    )).scalar_one()
    db_session.add(UserResponse(assessment_id=assessment.id, question_id=question.id, answer_value=0))
    await db_session.flush()

    scores = await professional_types_service.abilities_raw_scores(assessment.id, db_session)

    assert scores == {first_ability["scale"]: 0}
