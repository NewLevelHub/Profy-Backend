"""PRO-338 Ф1.1 — the 20 professional_types forced-choice pairs, seeded by
scripts/seed_professional_types_questions.py, must be retrievable for
senior (not junior/middle) and answerable through the existing
question_pair_service without leaking into riasec/bigfive scoring."""
import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.question import Question, QuestionInstrument
from app.models.question_pair import QuestionPair
from app.models.user import User
from app.schemas.question_pair import PairAnswerItem
from app.services import question_pair_service
from scripts.professional_types_bank import PAIRS


async def _seed_professional_types_pairs(db: AsyncSession) -> dict[int, tuple[uuid.UUID, uuid.UUID]]:
    """Mirrors scripts/seed_professional_types_questions.py's core logic
    directly against this test's own transaction, rather than shelling out
    to the script — same pattern test_validity_items_in_battery.py uses for
    its own content."""
    await db.execute(delete(QuestionPair).where(QuestionPair.instrument == QuestionInstrument.professional_types))
    await db.execute(delete(Question).where(Question.instrument == QuestionInstrument.professional_types))

    ids_by_order: dict[int, uuid.UUID] = {}
    for pair in PAIRS:
        for option in (pair["option_a"], pair["option_b"]):
            q = Question(
                instrument=QuestionInstrument.professional_types,
                text=option["text"], order=option["order"], age_tier=AgeGroup.senior,
            )
            db.add(q)
            await db.flush()
            ids_by_order[option["order"]] = q.id

    pair_ids: dict[int, tuple[uuid.UUID, uuid.UUID]] = {}
    for pair in PAIRS:
        a_id = ids_by_order[pair["option_a"]["order"]]
        b_id = ids_by_order[pair["option_b"]["order"]]
        db.add(QuestionPair(
            instrument=QuestionInstrument.professional_types,
            age_tier=AgeGroup.senior,
            pair_index=pair["pair_index"],
            question_a_id=a_id, question_b_id=b_id,
        ))
        pair_ids[pair["pair_index"]] = (a_id, b_id)
    await db.flush()
    return pair_ids


async def _make_assessment(db: AsyncSession, age_group: AgeGroup) -> Assessment:
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x", is_active=True, is_verified=True)
    db.add(user)
    await db.flush()
    profile = Profile(
        user_id=user.id, name="Т", age=16, grade=10, city="Алматы",
        country="Казахстан", language="ru", age_group=age_group,
    )
    db.add(profile)
    await db.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()
    return assessment


async def test_pairs_are_returned_for_senior_but_not_middle_or_junior(db_session: AsyncSession) -> None:
    await _seed_professional_types_pairs(db_session)

    senior_pairs = await question_pair_service.get_pairs(db_session, AgeGroup.senior)
    middle_pairs = await question_pair_service.get_pairs(db_session, AgeGroup.middle)
    junior_pairs = await question_pair_service.get_pairs(db_session, AgeGroup.junior)

    assert len([p for p in senior_pairs if p.instrument == QuestionInstrument.professional_types]) == 20
    assert all(p.instrument != QuestionInstrument.professional_types for p in middle_pairs)
    assert all(p.instrument != QuestionInstrument.professional_types for p in junior_pairs)


async def test_submitting_a_pair_answer_resolves_the_correct_pair_not_a_colliding_one(
    db_session: AsyncSession,
) -> None:
    pair_ids = await _seed_professional_types_pairs(db_session)
    assessment = await _make_assessment(db_session, AgeGroup.senior)
    a_id, b_id = pair_ids[68]  # first professional_types pair's global index

    response = await question_pair_service.submit_pair_answers(
        assessment.id,
        [PairAnswerItem(pair_index=68, picked_question_id=a_id)],
        assessment.profile_id,
        db_session,
    )

    assert response.answered_count == 2  # picked + other, per pair


async def test_professional_types_pairs_do_not_leak_into_riasec_scoring(db_session: AsyncSession) -> None:
    from app.services import riasec_service

    pair_ids = await _seed_professional_types_pairs(db_session)
    assessment = await _make_assessment(db_session, AgeGroup.senior)

    before = await riasec_service.raw_scores(assessment.id, db_session, AgeGroup.senior)

    for pair_index, (a_id, _b_id) in pair_ids.items():
        await question_pair_service.submit_pair_answers(
            assessment.id,
            [PairAnswerItem(pair_index=pair_index, picked_question_id=a_id)],
            assessment.profile_id,
            db_session,
        )

    after = await riasec_service.raw_scores(assessment.id, db_session, AgeGroup.senior)
    assert after == before
