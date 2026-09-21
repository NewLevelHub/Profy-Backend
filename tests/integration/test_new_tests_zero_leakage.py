"""PRO-338 Ф0.5/Ф1.10 — the new Likert/binary-based instruments added in Ф0.2
(professional_types_abilities, eysenck, elers, boyko_empathy, kondash_anxiety —
professional_types itself is QuestionPair-based, not Question-based, so it
never reaches the Likert battery at all) must have zero leakage into
riasec/bigfive/mi scoring, same
guarantee PRO-298 already established for `validity`
(test_validity_items_in_battery.py::test_validity_rows_do_not_change_riasec_or_bigfive_scoring)
— every scoring service filters strictly on `Question.instrument ==` its
own value, so an unrelated instrument's answered rows must never move its
score, and `assessment_shared.likert_total_questions` must count the new
rows automatically (instrument-agnostic by construction — no code change
needed per Ф0.5, only this regression guard)."""
import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.question import BigFiveDomain, HollandType, Keyed, MIType, Question, QuestionInstrument
from app.models.user import User
from app.models.user_response import UserResponse
from app.services import assessment_shared, bigfive_service, mi_service, riasec_service

_HOLLAND = list(HollandType)
_BIG_FIVE_DOMAINS = list(BigFiveDomain)
_MI = list(MIType)
_NEW_INSTRUMENTS = [
    QuestionInstrument.professional_types_abilities,
    QuestionInstrument.eysenck,
    QuestionInstrument.elers,
    QuestionInstrument.boyko_empathy,
    QuestionInstrument.kondash_anxiety,
]


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


async def _seed_new_instrument_questions(db: AsyncSession, *, n_per_instrument: int = 5) -> list[Question]:
    questions: list[Question] = []
    for offset, instrument in enumerate(_NEW_INSTRUMENTS):
        for i in range(n_per_instrument):
            q = Question(
                instrument=instrument, text={"ru": f"{instrument.value} {i}"},
                order=2000 + offset * 100 + i, age_tier=AgeGroup.senior,
            )
            db.add(q)
            questions.append(q)
    await db.flush()
    return questions


async def test_new_instruments_do_not_change_riasec_or_bigfive_scoring(db_session: AsyncSession) -> None:
    await db_session.execute(delete(Question))
    assessment = await _make_assessment(db_session, AgeGroup.senior)

    riasec_questions = [
        Question(
            instrument=QuestionInstrument.riasec, riasec_type=_HOLLAND[i % len(_HOLLAND)],
            text={"ru": f"riasec {i}"}, order=1 + i, age_tier=AgeGroup.senior,
        )
        for i in range(12)
    ]
    bigfive_questions = [
        Question(
            instrument=QuestionInstrument.big_five, bigfive_domain=_BIG_FIVE_DOMAINS[i % 5],
            keyed=Keyed.plus if i % 2 else Keyed.minus, facet=1,
            text={"ru": f"bigfive {i}"}, order=100 + i, age_tier=AgeGroup.senior,
        )
        for i in range(10)
    ]
    db_session.add_all([*riasec_questions, *bigfive_questions])
    await db_session.flush()

    for q in [*riasec_questions, *bigfive_questions]:
        db_session.add(UserResponse(assessment_id=assessment.id, question_id=q.id, answer_value=4))
    await db_session.flush()

    riasec_before = await riasec_service.raw_scores(assessment.id, db_session, AgeGroup.senior)
    bigfive_before = await bigfive_service.raw_scores(assessment.id, db_session, AgeGroup.senior, mean_answer=4.0)

    # Add the 4 new instruments' questions AND answer every one of them —
    # the whole point of the guarantee is that scoring ignores them even
    # when they're fully present and answered, not just when absent.
    new_questions = await _seed_new_instrument_questions(db_session)
    for q in new_questions:
        db_session.add(UserResponse(assessment_id=assessment.id, question_id=q.id, answer_value=2))
    await db_session.flush()

    riasec_after = await riasec_service.raw_scores(assessment.id, db_session, AgeGroup.senior)
    bigfive_after = await bigfive_service.raw_scores(assessment.id, db_session, AgeGroup.senior, mean_answer=4.0)

    assert riasec_after == riasec_before
    assert bigfive_after == bigfive_before


async def test_new_instruments_do_not_change_mi_scoring_for_junior(db_session: AsyncSession) -> None:
    await db_session.execute(delete(Question))
    assessment = await _make_assessment(db_session, AgeGroup.junior)

    mi_questions = [
        Question(
            instrument=QuestionInstrument.mi, mi_category=_MI[i % len(_MI)],
            text={"ru": f"mi {i}"}, order=1 + i, age_tier=AgeGroup.junior,
        )
        for i in range(16)
    ]
    db_session.add_all(mi_questions)
    await db_session.flush()
    for q in mi_questions:
        db_session.add(UserResponse(assessment_id=assessment.id, question_id=q.id, answer_value=4))
    await db_session.flush()

    mi_before = await mi_service.raw_scores(assessment.id, db_session, AgeGroup.junior)

    new_questions = await _seed_new_instrument_questions(db_session)
    for q in new_questions:
        db_session.add(UserResponse(assessment_id=assessment.id, question_id=q.id, answer_value=2))
    await db_session.flush()

    mi_after = await mi_service.raw_scores(assessment.id, db_session, AgeGroup.junior)

    assert mi_after == mi_before


async def test_likert_total_questions_counts_new_instruments_automatically(db_session: AsyncSession) -> None:
    """The other half of Ф0.5's backend claim: no counter change was needed
    because `likert_total_questions` counts every `age_tier`-visible row
    regardless of `instrument` — confirmed here rather than just asserted in
    the ticket."""
    await db_session.execute(delete(Question))
    before = await assessment_shared.likert_total_questions(db_session, AgeGroup.senior)
    assert before == 0

    await _seed_new_instrument_questions(db_session, n_per_instrument=7)

    after = await assessment_shared.likert_total_questions(db_session, AgeGroup.senior)
    assert after == 7 * len(_NEW_INSTRUMENTS)
