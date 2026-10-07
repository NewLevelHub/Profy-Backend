"""PRO-338 Ф2.3 — the belbin_runs table/model shape: one run per assessment
(`assessment_id` unique — Belbin is never retaken alone), cascade on delete."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.belbin_run import BelbinRun
from app.models.profile import AgeGroup, Profile
from app.models.user import User


async def _make_assessment(db: AsyncSession) -> tuple[Assessment, User]:
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
    return assessment, user


def _sample_allocations() -> list[dict[str, int]]:
    # 7 blocks x 8 items, 10 points per block — shape only, values arbitrary
    # for this model-shape test (real validation is ipsative_battery.py, Ф0.6).
    return [
        {f"s{section}_{item}": (10 if item == 0 else 0) for item in range(8)}
        for section in range(7)
    ]


async def test_a_belbin_run_can_be_inserted_and_read_back(db_session: AsyncSession) -> None:
    assessment, user = await _make_assessment(db_session)
    role_totals = {"implementer": 30, "coordinator": 10, "shaper": 10, "plant": 10,
                    "resource_investigator": 10, "evaluator": 10, "teamworker": 10, "finisher": 10}

    run = BelbinRun(
        assessment_id=assessment.id, user_id=user.id,
        allocations=_sample_allocations(), role_totals=role_totals,
    )
    db_session.add(run)
    await db_session.flush()

    fetched = (await db_session.execute(
        select(BelbinRun).where(BelbinRun.assessment_id == assessment.id)
    )).scalar_one()
    assert fetched.role_totals == role_totals
    assert len(fetched.allocations) == 7
    assert fetched.created_at is not None


async def test_one_run_per_assessment_is_enforced_by_the_database(db_session: AsyncSession) -> None:
    # The submit endpoint answers 409 first; the unique index also stops a
    # concurrent second submit from slipping through.
    assessment, user = await _make_assessment(db_session)
    allocations = _sample_allocations()

    db_session.add(BelbinRun(
        assessment_id=assessment.id, user_id=user.id,
        allocations=allocations, role_totals={"implementer": 70},
    ))
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(BelbinRun(
                assessment_id=assessment.id, user_id=user.id,
                allocations=allocations, role_totals={"implementer": 20, "coordinator": 50},
            ))


async def test_deleting_the_assessment_cascades_to_its_belbin_runs(db_session: AsyncSession) -> None:
    assessment, user = await _make_assessment(db_session)
    db_session.add(BelbinRun(
        assessment_id=assessment.id, user_id=user.id,
        allocations=_sample_allocations(), role_totals={"implementer": 70},
    ))
    await db_session.flush()

    await db_session.delete(assessment)
    await db_session.flush()

    rows = (await db_session.execute(
        select(BelbinRun).where(BelbinRun.assessment_id == assessment.id)
    )).scalars().all()
    assert rows == []
