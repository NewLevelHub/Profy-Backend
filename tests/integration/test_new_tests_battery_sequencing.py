"""PRO-338 Ф0.8 — professional_types_abilities/eysenck/elers must render as
ONE contiguous, non-interleaved sub-section after MI/RIASEC/BigFive — unlike
`validity` (PRO-298), which IS deliberately interleaved into the RIASEC
block. Mirrors test_validity_items_in_battery.py's battery-shape assertions,
but for the opposite property (no splicing, no gaps)."""
import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.question import BigFiveDomain, HollandType, Keyed, Question, QuestionInstrument
from app.models.user import User
from app.services import question_service
from scripts.elers_bank import QUESTIONS as ELERS_QUESTIONS
from scripts.eysenck_bank import QUESTIONS as EYSENCK_QUESTIONS
from scripts.professional_types_bank import QUESTIONS as PROFESSIONAL_TYPES_ABILITIES_QUESTIONS

_HOLLAND = list(HollandType)
_BIG_FIVE_DOMAINS = list(BigFiveDomain)
_NEW_TESTS_INSTRUMENTS = {
    QuestionInstrument.professional_types_abilities,
    QuestionInstrument.eysenck,
    QuestionInstrument.elers,
}


async def _seed_full_battery(db: AsyncSession) -> Assessment:
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

    # A dev DB that already ran the real seed_professional_types_questions.py/
    # seed_eysenck_questions.py/seed_elers_questions.py scripts (start.sh)
    # carries those real rows at the same `order` values this test uses —
    # drop them inside this test's rolled-back transaction so the count/
    # contiguity assertions below see exactly what this file seeds, same
    # precaution as test_validity_items_in_battery.py takes for `validity`.
    await db.execute(delete(Question).where(Question.instrument.in_(_NEW_TESTS_INSTRUMENTS)))

    for i in range(20):
        db.add(Question(
            instrument=QuestionInstrument.riasec, riasec_type=_HOLLAND[i % len(_HOLLAND)],
            text=f"riasec {i}", order=1 + i, age_tier=AgeGroup.senior,
        ))
    for i in range(10):
        db.add(Question(
            instrument=QuestionInstrument.big_five, bigfive_domain=_BIG_FIVE_DOMAINS[i % 5],
            keyed=Keyed.plus if i % 2 else Keyed.minus, facet=1,
            text=f"bigfive {i}", order=100 + i, age_tier=AgeGroup.senior,
        ))
    for data in PROFESSIONAL_TYPES_ABILITIES_QUESTIONS:
        db.add(Question(
            instrument=QuestionInstrument.professional_types_abilities,
            text=data["text"], order=data["order"], age_tier=AgeGroup(data["age_tier"]),
        ))
    for data in EYSENCK_QUESTIONS:
        db.add(Question(
            instrument=QuestionInstrument.eysenck,
            text=data["text"], order=data["order"], age_tier=AgeGroup(data["age_tier"]),
        ))
    for data in ELERS_QUESTIONS:
        db.add(Question(
            instrument=QuestionInstrument.elers,
            text=data["text"], order=data["order"], age_tier=AgeGroup(data["age_tier"]),
        ))
    await db.flush()
    return assessment


async def test_new_tests_form_one_contiguous_block_after_the_main_battery(
    db_session: AsyncSession,
) -> None:
    assessment = await _seed_full_battery(db_session)

    battery = await question_service.get_all_questions(
        db_session, AgeGroup.senior, assessment_id=assessment.id
    )

    new_test_positions = [i for i, q in enumerate(battery) if q.instrument in _NEW_TESTS_INSTRUMENTS]
    expected_count = (
        len(PROFESSIONAL_TYPES_ABILITIES_QUESTIONS) + len(EYSENCK_QUESTIONS) + len(ELERS_QUESTIONS)
    )
    assert len(new_test_positions) == expected_count

    # Contiguous: no gap between the first and last position of the block.
    assert new_test_positions == list(range(min(new_test_positions), max(new_test_positions) + 1))

    # Strictly after every riasec/bigfive item — never spliced into them.
    other_positions = [
        i for i, q in enumerate(battery) if q.instrument not in _NEW_TESTS_INSTRUMENTS
    ]
    assert max(other_positions) < min(new_test_positions)

    # Internal order matches the epic's own table order (test 1 ДДО, test 3
    # Айзенк, test 5 Элерс) — not required for correctness, but pins the
    # intentional choice made in start.sh/the bank files' order ranges.
    instruments_in_block = [battery[i].instrument for i in new_test_positions]
    assert instruments_in_block == (
        [QuestionInstrument.professional_types_abilities] * len(PROFESSIONAL_TYPES_ABILITIES_QUESTIONS)
        + [QuestionInstrument.eysenck] * len(EYSENCK_QUESTIONS)
        + [QuestionInstrument.elers] * len(ELERS_QUESTIONS)
    )


async def test_new_tests_never_leak_into_riasec_scoring_via_the_battery(
    db_session: AsyncSession,
) -> None:
    """Belt-and-suspenders alongside test_new_tests_zero_leakage.py: even
    when read through the same battery-building path a real client uses
    (not just a direct scoring-service call), the new instruments never
    show up tagged as riasec/big_five on the wire — no accidental masking
    like validity's (intentional) one."""
    assessment = await _seed_full_battery(db_session)

    battery = await question_service.get_all_questions(
        db_session, AgeGroup.senior, assessment_id=assessment.id
    )

    for q in battery:
        if q.instrument in _NEW_TESTS_INSTRUMENTS:
            assert q.riasec_type is None
            assert q.bigfive_domain is None
