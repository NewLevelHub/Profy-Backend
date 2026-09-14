"""Acceptance bar for the deterministic-fallback ticket: with the LLM
explicitly disabled, POST /result/generate (report_service.build_report)
must still succeed and return a complete, valid ResultResponseV2 — never an
error, never a partial shape. LLM is monkeypatched off explicitly rather
than relying on env state: this dev environment actually has a working
OpenAI key configured (LLM_ENABLED=true), so leaving it to the environment
would non-deterministically exercise the AI path instead of the fallback
this ticket is about.
"""

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.profile import AgeGroup, Profile
from app.models.question import HollandType, MIType, Question, QuestionInstrument
from app.models.user import User
from app.models.user_response import UserResponse
from app.schemas.result_v2 import DISCLAIMER, ResultResponseV2
from app.services import (
    assessment_shared,
    llm_client,
    mi_service,
    motivation_pair_service,
    motivation_service,
    report_service,
    riasec_service,
)

_AGE_SAMPLE = {AgeGroup.junior: 8, AgeGroup.middle: 12, AgeGroup.senior: 16}
# Far outside real seed data's order range (~300 real questions) — see
# test_age_matrix_full_flow.py's identical convention.
_SENTINEL_ORDER = 900_200


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


async def _seed_dominant_interest_signal(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, assessment: Assessment, age_group: AgeGroup,
) -> None:
    """A tiny, controlled RIASEC/MI signal so the deterministic fallback has
    real per-type differentiation to build strength-card evidence from.
    Without this, every type scores 0% on this assessment's zero real
    answers and riasec_service.strengths_weaknesses honestly returns no
    strengths (a deliberate anti-padding guard for a genuinely flat
    profile, see its own docstring) — correct in general, but not what
    these tests are pinning (report_version=2 wiring + a populated v2
    shape). question_counts is monkeypatched to match exactly what's
    seeded here, not the ~150 real rows already in the dev DB."""
    if age_group == AgeGroup.junior:
        service = mi_service
        category = MIType.logical
        questions = [
            Question(
                instrument=QuestionInstrument.mi, mi_category=category,
                text={"ru": f"test-mi-signal-{i}"}, age_tier=age_group, order=_SENTINEL_ORDER + i,
            )
            for i in range(3)
        ]
        counts = {c: (3 if c == category.value else 0) for c in mi_service.MI_ORDER}
    else:
        service = riasec_service
        rtype = HollandType.R
        questions = [
            Question(
                instrument=QuestionInstrument.riasec, riasec_type=rtype,
                text={"ru": f"test-riasec-signal-{i}"}, age_tier=age_group, order=_SENTINEL_ORDER + i,
            )
            for i in range(3)
        ]
        counts = {t: (3 if t == rtype.value else 0) for t in riasec_service.HOLLAND_ORDER}

    db_session.add_all(questions)
    await db_session.flush()
    db_session.add_all(
        UserResponse(assessment_id=assessment.id, question_id=q.id, answer_value=5) for q in questions
    )
    await db_session.flush()
    monkeypatch.setattr(service, "question_counts", AsyncMock(return_value=counts))


async def test_disabled_llm_returns_full_v2_form_for_senior(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch, senior=True)
    await _seed_dominant_interest_signal(db_session, monkeypatch, assessment, AgeGroup.senior)

    response = await report_service.build_report(assessment.id, db_session)

    assert isinstance(response, ResultResponseV2)
    assert response.report_version == 2
    assert response.interest_instrument == "riasec"
    assert len(response.interest_map) == 6
    assert response.summary
    assert response.disclaimer == DISCLAIMER
    assert response.strength_cards
    assert response.exploration_activities == []
    # careers may be empty only if no direction in the DB shares any Holland
    # letter with this (all-zero-score) profile's tie-broken top code — but
    # every field must still be well-formed either way.
    for career in response.careers:
        assert career.why

    stored = (
        await db_session.execute(select(AnalysisResult).where(AnalysisResult.assessment_id == assessment.id))
    ).scalar_one()
    assert stored.report_version == 2
    assert stored.strength_cards


async def test_disabled_llm_returns_full_v2_form_for_junior(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assessment = await _make_assessment(db_session, AgeGroup.junior)
    _force_complete_and_llm_disabled(monkeypatch, senior=False)
    await _seed_dominant_interest_signal(db_session, monkeypatch, assessment, AgeGroup.junior)

    response = await report_service.build_report(assessment.id, db_session)

    assert isinstance(response, ResultResponseV2)
    assert response.report_version == 2
    assert response.interest_instrument == "mi"
    assert len(response.interest_map) == 8
    assert response.careers == []
    assert response.exploration_activities
    assert response.summary
    assert response.disclaimer == DISCLAIMER
    assert response.strength_cards


async def test_get_report_after_generate_returns_the_same_v2_shape(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cache-hit path (report:v2:{id}) round-trips the exact same response —
    no silent reshaping/regeneration on a plain re-read."""
    assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch, senior=True)

    generated = await report_service.build_report(assessment.id, db_session)
    fetched = await report_service.get_report(assessment.id, db_session)

    assert fetched is not None
    assert fetched.model_dump() == generated.model_dump()


async def test_get_report_reshapes_from_storage_when_cache_is_cold(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DB-only path (report_service._shape_response): flush the Redis
    cache after generation and confirm a fresh read still reconstructs a
    valid, equivalent v2 response purely from the stored AnalysisResult row."""
    assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch, senior=True)

    generated = await report_service.build_report(assessment.id, db_session)

    redis = assessment_shared.get_redis()
    await redis.delete(f"report:v2:{assessment.id}")

    reshaped = await report_service.get_report(assessment.id, db_session)

    assert reshaped is not None
    assert reshaped.summary == generated.summary
    assert reshaped.interest_instrument == generated.interest_instrument
    assert [item.code for item in reshaped.interest_map] == [item.code for item in generated.interest_map]
    assert reshaped.is_flat_profile == generated.is_flat_profile
    assert [c.slug for c in reshaped.careers] == [c.slug for c in generated.careers]
