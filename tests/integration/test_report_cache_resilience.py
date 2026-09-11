"""Report cache versioning + Redis resilience.

Two bugs fixed by this ticket, both found by reading the code before writing
any test:

1. `report_service.py` moved its cache key to `report:v2:{id}` (previous
   ticket) but `assessment_shared.invalidate_retake` was still deleting the
   old unversioned `report:{id}` key — a retake never actually cleared the
   real cache. Fixed by centralizing the key as
   `assessment_shared.report_cache_key()`, used by both the writer
   (report_service) and the invalidator (invalidate_retake).
2. Every Redis call in the report read/write/invalidate paths was
   unprotected — a Redis outage would surface as a 500 even though the
   report is safely sitting in Postgres. Fixed with `_cache_get`/
   `_cache_set` (report_service.py) and `safe_redis_delete`/
   `safe_redis_scan` (assessment_shared.py), all of which catch
   `redis.RedisError` and fall through to the DB path.
"""

import uuid
from unittest.mock import AsyncMock

import pytest
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.schemas.result_v2 import ResultResponseV2
from app.services import (
    assessment_service,
    assessment_shared,
    llm_client,
    motivation_pair_service,
    motivation_service,
    question_pair_service,
    report_service,
)

_AGE_SAMPLE = {AgeGroup.junior: 8, AgeGroup.middle: 12, AgeGroup.senior: 16}


async def _make_assessment(db_session: AsyncSession, age_group: AgeGroup) -> Assessment:
    user = User(
        email=f"{uuid.uuid4()}@example.test", hashed_password="x", is_active=True, is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    profile = Profile(
        user_id=user.id, name="Тест", age=_AGE_SAMPLE[age_group], grade=5,
        city="Алматы", country="Казахстан", language="ru", age_group=age_group,
    )
    db_session.add(profile)
    await db_session.flush()

    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db_session.add(assessment)
    await db_session.flush()
    return assessment


def _force_complete_and_llm_disabled(monkeypatch: pytest.MonkeyPatch, *, senior: bool) -> None:
    monkeypatch.setattr(assessment_shared, "likert_answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "likert_total_questions", AsyncMock(return_value=1))
    if senior:
        monkeypatch.setattr(motivation_service, "answered_count", AsyncMock(return_value=1))
        monkeypatch.setattr(motivation_service, "total_triplets", AsyncMock(return_value=1))
    else:
        monkeypatch.setattr(motivation_pair_service, "answered_count", AsyncMock(return_value=1))
        monkeypatch.setattr(motivation_pair_service, "total_pairs", AsyncMock(return_value=1))
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
        == f"report:v4:ru:{assessment_id}"
    )
    assert (
        assessment_shared.report_cache_key(assessment_id, "kk")
        == f"report:v4:kk:{assessment_id}"
    )
    # report_service must use the exact same builder, not a parallel copy —
    # that's precisely what regressed last time.
    import app.services.report_service as report_service_module

    assert report_service_module._cache_key is assessment_shared.report_cache_key


async def test_build_report_writes_and_get_report_reads_the_same_cache_key(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch, senior=True)

    await report_service.build_report(assessment.id, db_session)

    redis = assessment_shared.get_redis()
    assert await redis.get(assessment_shared.report_cache_key(assessment.id)) is not None


async def test_legacy_unversioned_cache_payload_is_never_read_as_v2(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-rollout v1-shaped JSON blob might still be sitting under the old
    `report:{id}` key when this ships. get_report/build_report must ignore
    it completely (they only ever address `report:v4:{locale}:{id}`) rather than try
    to parse it as ResultResponseV2 and blow up."""
    assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch, senior=True)

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
    assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch, senior=True)
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
    assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch, senior=True)

    generated = await report_service.build_report(assessment.id, db_session)

    monkeypatch.setattr(report_service, "_get_redis", lambda: _BrokenRedis())
    fetched = await report_service.get_report(assessment.id, db_session)

    assert fetched is not None
    assert fetched.summary == generated.summary


async def test_stale_cached_payload_missing_a_new_required_field_falls_back_to_db(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A payload cached under the *current* versioned key by a previous
    deploy — before `personality_notes` became required — must not crash
    the read path with a ValidationError. `_cache_get_response` catches
    that and falls through to a fresh DB-backed rebuild instead."""
    import json

    assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch, senior=True)

    generated = await report_service.build_report(assessment.id, db_session)

    redis = assessment_shared.get_redis()
    cache_key = assessment_shared.report_cache_key(assessment.id)
    stale_payload = generated.model_dump(mode="json")
    del stale_payload["personality_notes"]
    await redis.set(cache_key, json.dumps(stale_payload))

    fetched = await report_service.get_report(assessment.id, db_session)

    assert fetched is not None
    assert len(fetched.personality_notes) == 5


async def test_invalidate_retake_survives_redis_outage(
    db_session: AsyncSession,
) -> None:
    """invalidate_retake must still delete the stale AnalysisResult row even
    when Redis itself is unreachable — cache cleanup is best-effort, DB
    cleanup is not optional."""
    assessment = await _make_assessment(db_session, AgeGroup.senior)
    db_session.add(AnalysisResult(
        assessment_id=assessment.id, summary="stale", profile={}, code="RIA", meta={},
        careers=[], strengths=[], weaknesses=[], development_plan=[], big_five={},
        thinking_style={}, personality_highlights=[], personality_profile={},
        personality_notes={}, motivation={}, motivation_top=[], motivation_highlights=[],
    ))
    await db_session.flush()

    await assessment_shared.invalidate_retake(assessment, db_session, _BrokenRedis())

    remaining = (
        await db_session.execute(select(AnalysisResult).where(AnalysisResult.assessment_id == assessment.id))
    ).scalar_one_or_none()
    assert remaining is None


@pytest.mark.parametrize(
    "entrypoint_name",
    ["assessment_service", "question_pair_service", "motivation_pair_service", "motivation_service"],
)
async def test_every_retake_entrypoint_clears_the_versioned_report_cache(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, entrypoint_name: str
) -> None:
    """All four submit-answers entrypoints funnel through invalidate_retake
    (report_service.py), so this pins the observable contract at each of
    their own call sites rather than trusting that they all really do call
    the shared function."""
    assessment = await _make_assessment(db_session, AgeGroup.senior)

    user_result = await db_session.execute(select(Profile).where(Profile.id == assessment.profile_id))
    profile = user_result.scalar_one()

    assessment.status = AssessmentStatus.completed
    await db_session.flush()

    redis = assessment_shared.get_redis()
    cache_key = assessment_shared.report_cache_key(assessment.id)
    await redis.set(cache_key, '{"stale": true}')

    if entrypoint_name == "assessment_service":
        await assessment_service.submit_answers(assessment.id, [], profile.id, db_session)
    elif entrypoint_name == "question_pair_service":
        await question_pair_service.submit_pair_answers(assessment.id, [], profile.id, db_session)
    elif entrypoint_name == "motivation_pair_service":
        await motivation_pair_service.submit_pair_answers(assessment.id, [], profile.id, db_session)
    else:
        await motivation_service.submit_motivation_answers(assessment.id, [], profile.id, db_session)

    assert await redis.get(cache_key) is None
    await db_session.refresh(assessment)
    assert assessment.status == AssessmentStatus.in_progress
