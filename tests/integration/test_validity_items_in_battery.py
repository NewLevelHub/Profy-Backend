"""PRO-298: the protocol-validity items are woven into the Likert battery
returned by `/questions` — masked as Big Five, spread through the Big Five
block, deterministic per assessment — and they do NOT leak into RIASEC /
Big Five scoring (those filter by `instrument`)."""
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.question import (
    BigFiveDomain,
    HollandType,
    Keyed,
    MIType,
    Question,
    QuestionInstrument,
    ValidityRole,
)
from app.models.user import User
from app.models.user_response import UserResponse
from app.services import bigfive_service, question_service, riasec_service

_BIG_FIVE_DOMAINS = list(BigFiveDomain)
_HOLLAND = list(HollandType)
_MI = list(MIType)


async def _seed_battery(
    db: AsyncSession, *, n_bigfive: int = 80, n_validity: int = 25
) -> tuple[Assessment, list[uuid.UUID]]:
    user = User(
        email=f"{uuid.uuid4()}@example.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
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

    # A dev DB that already ran seed_lie_scale_questions.py carries the 25
    # real validity rows; drop them inside this test's rolled-back transaction
    # so the battery shape assertions see exactly what this file seeds.
    await db.execute(delete(Question).where(Question.instrument == QuestionInstrument.validity))

    # A realistic senior battery shape: RIASEC block, then Big Five block,
    # then MI block (contiguous `order` ranges — matches the seed banks).
    for i, holland in enumerate(_HOLLAND):
        db.add(Question(
            instrument=QuestionInstrument.riasec, riasec_type=holland,
            text=f"riasec {i}", order=1 + i, age_tier=AgeGroup.senior,
        ))
    for i in range(n_bigfive):
        db.add(Question(
            instrument=QuestionInstrument.big_five,
            bigfive_domain=_BIG_FIVE_DOMAINS[i % 5],
            keyed=Keyed.plus if i % 2 else Keyed.minus,
            facet=1, text=f"bigfive {i}", order=100 + i, age_tier=AgeGroup.senior,
        ))
    for i, mi in enumerate(_MI * 4):
        db.add(Question(
            instrument=QuestionInstrument.mi, mi_category=mi,
            text=f"mi {i}", order=500 + i, age_tier=AgeGroup.senior,
        ))

    validity_ids: list[uuid.UUID] = []
    for i in range(n_validity):
        q = Question(
            instrument=QuestionInstrument.validity,
            validity_role=ValidityRole.sd_key if i < 20 else ValidityRole.infrequency,
            validity_meta={"key": f"v{i:02d}", "keyed": "agree"},
            text=f"validity {i}", order=1000 + i, age_tier=AgeGroup.middle,
        )
        db.add(q)
        await db.flush()
        validity_ids.append(q.id)
    await db.flush()
    return assessment, validity_ids


async def test_validity_items_are_masked_and_woven_into_the_battery(
    db_session: AsyncSession,
) -> None:
    assessment, validity_ids = await _seed_battery(db_session)
    vset = set(validity_ids)

    battery = await question_service.get_all_questions(
        db_session, AgeGroup.senior, assessment_id=assessment.id
    )

    seen = [q for q in battery if q.id in vset]
    assert {q.id for q in seen} == vset, "every validity item present exactly once"
    for q in seen:
        assert q.instrument == QuestionInstrument.big_five  # masked on the wire
        assert q.bigfive_domain is None
        assert q.riasec_type is None

    # order is dense 1..N and matches list position (the client re-sorts by it)
    assert [q.order for q in battery] == list(range(1, len(battery) + 1))

    positions = [i for i, q in enumerate(battery) if q.id in vset]
    assert min(positions) >= 10, "not in the first ~10 of the battery"
    assert max(positions) <= len(battery) - 1 - 10, "not in the last ~10"
    gaps = [b - a for a, b in zip(positions, positions[1:])]
    assert min(gaps) >= 3, "no two validity items back-to-back"
    assert len(set(gaps)) > 1, "not a fixed 'every Nth' pattern"

    # every validity item sits strictly inside the Big Five block, so it is
    # surrounded by Big-Five-scaled items and reads identically
    bf_positions = [
        i for i, q in enumerate(battery)
        if q.instrument == QuestionInstrument.big_five and q.id not in vset
    ]
    assert min(bf_positions) < min(positions)
    assert max(positions) < max(bf_positions)


async def test_battery_is_deterministic_per_assessment(db_session: AsyncSession) -> None:
    assessment, _ = await _seed_battery(db_session)

    first = await question_service.get_all_questions(
        db_session, AgeGroup.senior, assessment_id=assessment.id
    )
    second = await question_service.get_all_questions(
        db_session, AgeGroup.senior, assessment_id=assessment.id
    )
    assert [q.id for q in first] == [q.id for q in second]


async def test_validity_rows_do_not_change_riasec_or_bigfive_scoring(
    db_session: AsyncSession,
) -> None:
    assessment, _ = await _seed_battery(db_session)

    real = (await db_session.execute(
        select(Question).where(Question.instrument != QuestionInstrument.validity)
    )).scalars().all()
    validity = (await db_session.execute(
        select(Question).where(Question.instrument == QuestionInstrument.validity)
    )).scalars().all()
    # Answer the real items AND the validity items — scoring must ignore the latter.
    for q in [*real, *validity]:
        db_session.add(UserResponse(
            assessment_id=assessment.id, question_id=q.id, answer_value=4
        ))
    await db_session.flush()

    riasec_with = await riasec_service.raw_scores(assessment.id, db_session, AgeGroup.senior)
    bigfive_with = await bigfive_service.raw_scores(assessment.id, db_session, AgeGroup.senior)
    bf_counts_with = await bigfive_service.question_counts(db_session, AgeGroup.senior)

    # The "before PRO-298" world: no validity rows at all. Re-score the
    # identical answers to the real items.
    await db_session.execute(
        delete(UserResponse).where(UserResponse.question_id.in_([q.id for q in validity]))
    )
    await db_session.execute(
        delete(Question).where(Question.instrument == QuestionInstrument.validity)
    )
    await db_session.flush()

    assert await riasec_service.raw_scores(assessment.id, db_session, AgeGroup.senior) == riasec_with
    assert await bigfive_service.raw_scores(assessment.id, db_session, AgeGroup.senior) == bigfive_with
    assert await bigfive_service.question_counts(db_session, AgeGroup.senior) == bf_counts_with


async def test_no_validity_rows_leaves_the_battery_untouched(db_session: AsyncSession) -> None:
    assessment, _ = await _seed_battery(db_session, n_validity=0)
    battery = await question_service.get_all_questions(
        db_session, AgeGroup.senior, assessment_id=assessment.id
    )
    assert [q.order for q in battery] == list(range(1, len(battery) + 1))
    assert all(q.instrument != QuestionInstrument.validity for q in battery)
