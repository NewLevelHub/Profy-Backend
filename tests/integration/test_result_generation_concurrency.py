"""Idempotency/concurrency ticket: two concurrent POST /result/generate for
the same assessment must not run two independent generation passes, must
never create a second AnalysisResult row, and must hand back identical
responses.

Needs two genuinely separate DB connections racing each other — the shared
`db_session` fixture (tests/conftest.py) binds everything to one connection/
savepoint, which can't run two queries concurrently and, more importantly,
a second real connection wouldn't see the first's uncommitted setup rows at
all (Postgres MVCC). So this file opens its own sessions against the real
dev DB and cleans up its own rows explicitly (same "real shared DB, delete
what you added" discipline as docs/rs-progress-notes.md for other cases
that need genuine concurrency/global state).
"""
import asyncio
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock

from app.database import engine
from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import assessment_shared, llm_client, motivation_service, report_service


async def _make_committed_senior_assessment() -> uuid.UUID:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        user = User(
            email=f"{uuid.uuid4()}@example.test", hashed_password="x", is_active=True, is_verified=True,
        )
        session.add(user)
        await session.flush()
        profile = Profile(
            user_id=user.id, name="Тест", age=16, grade=10,
            city="Алматы", country="Казахстан", language="ru", age_group=AgeGroup.senior,
        )
        session.add(profile)
        await session.flush()
        assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
        session.add(assessment)
        await session.commit()
        return assessment.id


async def _cleanup(assessment_id: uuid.UUID) -> None:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        assessment = (
            await session.execute(select(Assessment).where(Assessment.id == assessment_id))
        ).scalar_one_or_none()
        if assessment is None:
            return
        profile_id = assessment.profile_id
        await session.execute(delete(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id))
        await session.execute(delete(Assessment).where(Assessment.id == assessment_id))
        profile = (await session.execute(select(Profile).where(Profile.id == profile_id))).scalar_one_or_none()
        if profile is not None:
            user_id = profile.user_id
            await session.execute(delete(Profile).where(Profile.id == profile_id))
            await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def test_concurrent_generate_runs_narrative_generation_once_and_returns_identical_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)  # deterministic fallback, no real LLM cost
    monkeypatch.setattr(assessment_shared, "likert_answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "likert_total_questions", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "total_triplets", AsyncMock(return_value=1))

    call_count = 0
    real_generate = report_service.generate_report_narrative

    async def _counting_generate(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return await real_generate(*args, **kwargs)

    monkeypatch.setattr(report_service, "generate_report_narrative", _counting_generate)

    assessment_id = await _make_committed_senior_assessment()
    try:
        async def _generate() -> report_service.ResultResponseV2:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                return await report_service.build_report(assessment_id, session)

        first, second = await asyncio.gather(_generate(), _generate())

        assert call_count == 1, "narrative generation must run exactly once across the race, not twice"
        assert first.model_dump() == second.model_dump()

        async with AsyncSession(engine, expire_on_commit=False) as session:
            rows = (
                await session.execute(
                    select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
                )
            ).scalars().all()
            assert len(rows) == 1

            assessment = (
                await session.execute(select(Assessment).where(Assessment.id == assessment_id))
            ).scalar_one()
            assert assessment.status == AssessmentStatus.completed
    finally:
        await _cleanup(assessment_id)


async def test_repeat_post_after_generation_does_not_regenerate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)
    monkeypatch.setattr(assessment_shared, "likert_answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "likert_total_questions", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "total_triplets", AsyncMock(return_value=1))

    call_count = 0
    real_generate = report_service.generate_report_narrative

    async def _counting_generate(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return await real_generate(*args, **kwargs)

    monkeypatch.setattr(report_service, "generate_report_narrative", _counting_generate)

    assessment_id = await _make_committed_senior_assessment()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            first = await report_service.build_report(assessment_id, session)
        assert call_count == 1

        # A second POST (cold cache: fresh process would still hit Redis, but
        # here we drop it explicitly to force the DB-only reshape path) must
        # read the already-stored row, not regenerate.
        redis = assessment_shared.get_redis()
        await redis.delete(assessment_shared.report_cache_key(assessment_id))

        async with AsyncSession(engine, expire_on_commit=False) as session:
            second = await report_service.build_report(assessment_id, session)

        assert call_count == 1, "a repeat POST must not call narrative generation again"
        assert first.model_dump() == second.model_dump()
    finally:
        await _cleanup(assessment_id)
