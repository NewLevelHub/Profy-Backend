"""KZ-403 (end-to-end) — with the LLM off, a `locale='kk'` student's
`/results` renders in Kazakh: the deterministic narrative summary/final
analysis, the interest-map spheres and note, the personality note, and the
career "why" strings all come back Kazakh, driven by the artifact owner's
`users.locale` rather than any request locale.
"""
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import (
    assessment_shared,
    llm_client,
    motivation_pair_service,
    motivation_service,
    report_service,
)

_KK_CHARS = set("әғқңөұүһі")


async def _kk_assessment(db_session: AsyncSession, age_group: AgeGroup, age: int) -> Assessment:
    user = User(
        email=f"{uuid.uuid4()}@example.com", hashed_password="x",
        is_active=True, is_verified=True, locale="kk",
    )
    db_session.add(user)
    await db_session.flush()
    profile = Profile(
        user_id=user.id, name="Тест", age=age, grade=9,
        city="Алматы", country="Қазақстан", language="қазақша", age_group=age_group,
    )
    db_session.add(profile)
    await db_session.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db_session.add(assessment)
    await db_session.flush()
    return assessment


def _force_complete_llm_off(monkeypatch: pytest.MonkeyPatch, *, senior: bool) -> None:
    monkeypatch.setattr(assessment_shared, "likert_answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "likert_total_questions", AsyncMock(return_value=1))
    if senior:
        monkeypatch.setattr(motivation_service, "answered_count", AsyncMock(return_value=1))
        monkeypatch.setattr(motivation_service, "total_triplets", AsyncMock(return_value=1))
    else:
        monkeypatch.setattr(motivation_pair_service, "answered_count", AsyncMock(return_value=1))
        monkeypatch.setattr(motivation_pair_service, "total_pairs", AsyncMock(return_value=1))
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)


def _is_kk(text: str) -> bool:
    return bool(_KK_CHARS & set(text.lower()))


async def test_kk_owner_gets_a_kazakh_deterministic_report(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assessment = await _kk_assessment(db_session, AgeGroup.senior, 16)
    _force_complete_llm_off(monkeypatch, senior=True)

    response = await report_service.build_report(assessment.id, db_session)

    assert _is_kk(response.summary), response.summary
    assert _is_kk(response.final_analysis), response.final_analysis
    assert _is_kk(response.interest_map_note), response.interest_map_note
    assert _is_kk(response.personality_note), response.personality_note
    # every interest-map sphere label is Kazakh (riasec_labels() under kk)
    assert all(_is_kk(item.sphere) for item in response.interest_map)
    assert "Реалистичный" not in {item.sphere for item in response.interest_map}


async def test_kk_report_is_stable_on_cold_cache_reshape(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_report()/_shape_response recomputes the synthesis text — it must
    also honour the owner locale, not fall back to ru."""
    assessment = await _kk_assessment(db_session, AgeGroup.senior, 17)
    _force_complete_llm_off(monkeypatch, senior=True)

    await report_service.build_report(assessment.id, db_session)
    # cold cache: force the storage-reshape path
    monkeypatch.setattr(report_service, "_cache_get_response", AsyncMock(return_value=None))
    reshaped = await report_service.get_report(assessment.id, db_session)

    assert reshaped is not None
    assert _is_kk(reshaped.interest_map_note), reshaped.interest_map_note
    assert _is_kk(reshaped.personality_note), reshaped.personality_note
    assert all(_is_kk(item.sphere) for item in reshaped.interest_map)


async def test_ru_owner_report_is_unaffected(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x",
                is_active=True, is_verified=True)  # locale defaults to ru
    db_session.add(user)
    await db_session.flush()
    profile = Profile(user_id=user.id, name="Тест", age=16, grade=9, city="Алматы",
                      country="Казахстан", language="ru", age_group=AgeGroup.senior)
    db_session.add(profile)
    await db_session.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db_session.add(assessment)
    await db_session.flush()
    _force_complete_llm_off(monkeypatch, senior=True)

    response = await report_service.build_report(assessment.id, db_session)

    for text in (response.summary, response.final_analysis, response.interest_map_note,
                 response.personality_note):
        assert not (_KK_CHARS & set(text.lower())), text
    assert response.summary.startswith("По твоим ответам заметно")
    assert all(item.sphere in {
        "Реалистичный", "Исследовательский", "Артистичный",
        "Социальный", "Предприимчивый", "Конвенциональный",
    } for item in response.interest_map)
