"""PROFY-006: concurrent starts converge on one pending color-test run."""

import asyncio
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine
from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.psychoemotional_run import PsychoEmotionalRun
from app.models.user import User
from app.schemas.psychoemotional import StartPsychoEmotionalRequest
from app.services.psychoemotional import run_service


_PAYLOAD = StartPsychoEmotionalRequest(
    list1=[4, 3, 2, 1, 5, 6, 0, 7],
    list1_dt_ms=[0, 2100, 1800, 2400, 3000, 1500, 1200, 900],
    checkin={"q1": "calm", "q2": "skipped", "q3": "good"},
)


async def _make_committed_assessment() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        user = User(
            email=f"{uuid.uuid4()}@example.test",
            hashed_password="x",
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.flush()
        profile = Profile(
            user_id=user.id,
            name="Test",
            age=16,
            grade=10,
            city="Almaty",
            country="Kazakhstan",
            language="ru",
            age_group=AgeGroup.senior,
        )
        session.add(profile)
        await session.flush()
        assessment = Assessment(
            profile_id=profile.id,
            goal=AssessmentGoal.explore,
        )
        session.add(assessment)
        await session.commit()
        return user.id, profile.id, assessment.id


async def _cleanup(user_id: uuid.UUID, profile_id: uuid.UUID) -> None:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        await session.execute(delete(Profile).where(Profile.id == profile_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def test_two_concurrent_starts_return_the_same_pending_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, profile_id, assessment_id = await _make_committed_assessment()
    real_lookup = run_service._get_pending_run
    both_lookups_finished = asyncio.Event()
    arrivals = 0

    async def synchronized_lookup(*args, **kwargs):
        nonlocal arrivals
        result = await real_lookup(*args, **kwargs)
        if arrivals < 2:
            arrivals += 1
            if arrivals == 2:
                both_lookups_finished.set()
            await asyncio.wait_for(both_lookups_finished.wait(), timeout=5)
        return result

    monkeypatch.setattr(run_service, "_get_pending_run", synchronized_lookup)

    async def start() -> PsychoEmotionalRun:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            return await run_service.start_run(
                assessment_id,
                _PAYLOAD,
                user_id=user_id,
                db=session,
            )

    try:
        first, second = await asyncio.gather(start(), start())
        assert first.id == second.id

        async with AsyncSession(engine, expire_on_commit=False) as session:
            rows = (
                await session.execute(
                    select(PsychoEmotionalRun).where(
                        PsychoEmotionalRun.assessment_id == assessment_id,
                        PsychoEmotionalRun.list2.is_(None),
                    )
                )
            ).scalars().all()
            assert [row.id for row in rows] == [first.id]
    finally:
        await _cleanup(user_id, profile_id)
