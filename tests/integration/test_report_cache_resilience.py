"""Report cache versioning + Redis resilience.

The Postgres report is the source of truth. Redis read, write and invalidation
failures must fall through to the database instead of surfacing as HTTP 500.
"""

import uuid
from unittest.mock import AsyncMock

import pytest
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult, ReviewStatus
from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.schemas.result_v2 import ResultResponseV2
from app.services import assessment_shared, llm_client, motivation_service, report_service



async def _make_assessment(db_session: AsyncSession) -> Assessment:
    user = User(
        email=f"{uuid.uuid4()}@example.test", hashed_password="x", is_active=True, is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    profile = Profile(
        user_id=user.id, name="Тест", age=16, grade=5,
        city="Алматы", country="Казахстан", language="ru", age_group=AgeGroup.senior,
    )
    db_session.add(profile)
    await db_session.flush()

    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db_session.add(assessment)
    await db_session.flush()
    return assessment


def _force_complete_and_llm_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assessment_shared, "likert_answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "likert_total_questions", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "total_triplets", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "belbin_and_astur_completed", AsyncMock(return_value=True))
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)


class _BrokenRedis:
    """Stands in for a Redis client that's down: every operation this
    module might call raises the real redis-py connection error."""

    async def get(self, *_a, **_kw):
        raise aioredis.ConnectionError("simulated redis outage")

    async def setex(self, *_a, **_kw):
        raise aioredis.ConnectionError("simulated redis outage")

    async def delete(self, *_a, **_kw):
        raise aioredis.ConnectionError("simulated redis outage")

    async def scan_iter(self, *_a, **_kw):
        raise aioredis.ConnectionError("simulated redis outage")
        yield  # pragma: no cover - makes this an async generator function


async def test_report_cache_key_is_centralized_and_versioned() -> None:
    assessment_id = uuid.uuid4()
    assert (
        assessment_shared.report_cache_key(assessment_id)
        == f"report:v5:ru:{assessment_id}"
    )
    assert (
        assessment_shared.report_cache_key(assessment_id, "kk")
        == f"report:v5:kk:{assessment_id}"
    )
    # report_service must use the exact same builder, not a parallel copy —
    # that's precisely what regressed last time.
    import app.services.report_service as report_service_module

    assert report_service_module._cache_key is assessment_shared.report_cache_key


async def test_build_report_writes_and_get_report_reads_the_same_cache_key(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assessment = await _make_assessment(db_session)
    _force_complete_and_llm_disabled(monkeypatch)

    await report_service.build_report(assessment.id, db_session)

    # A freshly generated report is pending psychologist review (PRO-337)
    # and must never land in the student cache.
    redis = assessment_shared.get_redis()
    cache_key = assessment_shared.report_cache_key(assessment.id)
    assert await redis.get(cache_key) is None

    stored = (
        await db_session.execute(select(AnalysisResult).where(AnalysisResult.assessment_id == assessment.id))
    ).scalar_one()
    stored.review_status = ReviewStatus.published
    await db_session.flush()

    await report_service.get_report(assessment.id, db_session)
    try:
        assert await redis.get(cache_key) is not None
    finally:
        await redis.delete(cache_key)


async def test_legacy_unversioned_cache_payload_is_never_read_as_v2(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-rollout v1-shaped JSON blob might still be sitting under the old
    `report:{id}` key when this ships. get_report/build_report must ignore
    it completely (they only ever address `report:v5:{locale}:{id}`) rather than try
    to parse it as ResultResponseV2 and blow up."""
    assessment = await _make_assessment(db_session)
    _force_complete_and_llm_disabled(monkeypatch)

    redis = assessment_shared.get_redis()
    legacy_key = f"report:{assessment.id}"
    await redis.set(legacy_key, '{"not": "a valid v2 payload"}')

    try:
        response = await report_service.build_report(assessment.id, db_session)
        assert isinstance(response, ResultResponseV2)

        fetched = await report_service.get_report(assessment.id, db_session)
        assert fetched is not None
        assert fetched.model_dump() == response.model_dump()
    finally:
        await redis.delete(legacy_key)


async def test_build_report_survives_redis_outage_via_db(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assessment = await _make_assessment(db_session)
    _force_complete_and_llm_disabled(monkeypatch)
    monkeypatch.setattr(report_service, "_get_redis", lambda: _BrokenRedis())

    response = await report_service.build_report(assessment.id, db_session)

    assert isinstance(response, ResultResponseV2)
    stored = (
        await db_session.execute(select(AnalysisResult).where(AnalysisResult.assessment_id == assessment.id))
    ).scalar_one()
    assert stored.report_version == 2


async def test_get_report_survives_redis_outage_via_db(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assessment = await _make_assessment(db_session)
    _force_complete_and_llm_disabled(monkeypatch)

    generated = await report_service.build_report(assessment.id, db_session)

    monkeypatch.setattr(report_service, "_get_redis", lambda: _BrokenRedis())
    fetched = await report_service.get_report(assessment.id, db_session)

    assert fetched is not None
    assert fetched.summary == generated.summary


async def test_stale_cached_payload_missing_a_new_required_field_falls_back_to_db(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A payload cached under the *current* versioned key by a previous
    deploy — before some field became required — must not crash the read
    path with a ValidationError. `_cache_get_response` catches that and
    falls through to a fresh DB-backed rebuild instead.

    `thinking_style_notes` stands in for "a required field with no
    default" here — `personality_notes` used to be this ticket's example,
    but it's now optional/defaulted (docs/big-five-retirement.md: Big Five
    retired from the active pool, so a report with no personality data has
    0 cards, not a missing-required-field error), so deleting it from a
    cached payload no longer reproduces a validation failure at all."""
    import json

    assessment = await _make_assessment(db_session)
    _force_complete_and_llm_disabled(monkeypatch)

    generated = await report_service.build_report(assessment.id, db_session)

    redis = assessment_shared.get_redis()
    cache_key = assessment_shared.report_cache_key(assessment.id)
    stale_payload = generated.model_dump(mode="json")
    del stale_payload["thinking_style_notes"]
    await redis.set(cache_key, json.dumps(stale_payload))

    fetched = await report_service.get_report(assessment.id, db_session)

    assert fetched is not None
    assert fetched.thinking_style_notes == generated.thinking_style_notes
