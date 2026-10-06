"""PROFY-004: concurrent starts converge on one active assessment."""

import asyncio
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine
from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import assessment_service


async def _make_committed_profile(
    *, with_active_assessment: bool
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID | None]:
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
            name="Тест",
            age=16,
            grade=10,
            city="Алматы",
            country="Казахстан",
            language="ru",
            age_group=AgeGroup.senior,
        )
        session.add(profile)
        await session.flush()
        active = None
        if with_active_assessment:
            active = Assessment(
                profile_id=profile.id,
                goal=AssessmentGoal.explore,
                status=AssessmentStatus.in_progress,
            )
            session.add(active)
        await session.commit()
        return user.id, profile.id, active.id if active else None


async def _cleanup(user_id: uuid.UUID, profile_id: uuid.UUID) -> None:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        # Assessment children are removed by the profile -> assessment
        # cascade; Profile itself does not cascade from User.
        await session.execute(delete(Profile).where(Profile.id == profile_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


@pytest.mark.parametrize("with_active_assessment", [False, True])
async def test_two_concurrent_starts_return_the_same_active_assessment(
    monkeypatch: pytest.MonkeyPatch,
    with_active_assessment: bool,
) -> None:
    user_id, profile_id, replaced_id = await _make_committed_profile(
        with_active_assessment=with_active_assessment
    )
    real_lookup = assessment_service._get_in_progress_assessment
    both_lookups_finished = asyncio.Event()
    arrivals = 0

    async def synchronized_lookup(profile_id_arg, db):
        """Force both requests past the old check-before-insert window."""
        nonlocal arrivals
        result = await real_lookup(profile_id_arg, db)
        if arrivals < 2:
            arrivals += 1
            if arrivals == 2:
                both_lookups_finished.set()
            await asyncio.wait_for(both_lookups_finished.wait(), timeout=5)
        return result

    monkeypatch.setattr(
        assessment_service, "_get_in_progress_assessment", synchronized_lookup
    )

    async def start():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            return await assessment_service.create_assessment(
                profile_id, AssessmentGoal.profession, session
            )

    try:
        first, second = await asyncio.gather(start(), start())

        assert first.id == second.id
        assert first.status == second.status == AssessmentStatus.in_progress

        async with AsyncSession(engine, expire_on_commit=False) as session:
            active = (
                await session.execute(
                    select(Assessment).where(
                        Assessment.profile_id == profile_id,
                        Assessment.status == AssessmentStatus.in_progress,
                    )
                )
            ).scalars().all()
            assert [row.id for row in active] == [first.id]
            assert first.id != replaced_id
    finally:
        await _cleanup(user_id, profile_id)
