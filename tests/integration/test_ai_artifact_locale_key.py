"""KZ-405 — the report narrative (the only live AI artifact) is stored and
cached per (assessment, locale): a `ru` and a `kk` report for the same student
coexist and neither clobbers the other; reading a locale that was never
generated does not return the other locale's row.
"""
import json
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import (
    assessment_shared,
    llm_client,
    motivation_service,
    report_service,
)

_KK_CHARS = set("әғқңөұүһі")


async def _senior_assessment(db_session: AsyncSession, *, locale: str) -> tuple[Assessment, User]:
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x",
                is_active=True, is_verified=True, locale=locale)
    db_session.add(user)
    await db_session.flush()
    profile = Profile(user_id=user.id, name="Тест", age=16, grade=9, city="Алматы",
                      country="Қазақстан", language="ru", age_group=AgeGroup.senior)
    db_session.add(profile)
    await db_session.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db_session.add(assessment)
    await db_session.flush()
    return assessment, user


def _llm_off_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assessment_shared, "likert_answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "likert_total_questions", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "total_triplets", AsyncMock(return_value=1))
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)


async def _rows(db_session: AsyncSession, assessment_id: uuid.UUID) -> list[AnalysisResult]:
    return list((await db_session.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
    )).scalars().all())


async def test_ru_then_kk_generation_creates_two_independent_rows(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assessment, user = await _senior_assessment(db_session, locale="ru")
    _llm_off_complete(monkeypatch)

    ru_resp = await report_service.build_report(assessment.id, db_session)
    assert not (_KK_CHARS & set(ru_resp.summary.lower()))

    # student switches UI language to kk (KZ-106) and re-opens /results
    user.locale = "kk"
    await db_session.flush()
    redis = assessment_shared.get_redis()
    for key in assessment_shared.report_cache_keys(assessment.id):
        await redis.delete(key)

    kk_resp = await report_service.build_report(assessment.id, db_session)
    assert _KK_CHARS & set(kk_resp.summary.lower()), kk_resp.summary

    rows = await _rows(db_session, assessment.id)
    assert {r.locale for r in rows} == {"ru", "kk"}
    assert len(rows) == 2
    by_loc = {r.locale: r for r in rows}
    assert not (_KK_CHARS & set(by_loc["ru"].summary.lower()))
    assert _KK_CHARS & set(by_loc["kk"].summary.lower())
    # deterministic parts identical across locales
    assert by_loc["ru"].code == by_loc["kk"].code
    assert by_loc["ru"].strengths == by_loc["kk"].strengths


async def test_cache_keys_are_locale_scoped(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assessment, user = await _senior_assessment(db_session, locale="ru")
    _llm_off_complete(monkeypatch)
    await report_service.build_report(assessment.id, db_session)

    redis = assessment_shared.get_redis()
    ru_key = assessment_shared.report_cache_key(assessment.id, "ru")
    kk_key = assessment_shared.report_cache_key(assessment.id, "kk")
    assert ru_key != kk_key
    assert await redis.get(ru_key) is not None
    assert await redis.get(kk_key) is None


async def test_get_report_does_not_fall_back_to_another_locale(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # only a ru row exists; a kk-owner read must return None (-> KZ-406 regen),
    # never the ru row.
    assessment, user = await _senior_assessment(db_session, locale="ru")
    _llm_off_complete(monkeypatch)
    await report_service.build_report(assessment.id, db_session)

    user.locale = "kk"
    await db_session.flush()
    redis = assessment_shared.get_redis()
    for key in assessment_shared.report_cache_keys(assessment.id):
        await redis.delete(key)

    assert await report_service.get_report(assessment.id, db_session) is None
    # the ru row is untouched
    rows = await _rows(db_session, assessment.id)
    assert [r.locale for r in rows] == ["ru"]
