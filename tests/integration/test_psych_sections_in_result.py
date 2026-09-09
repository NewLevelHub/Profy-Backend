"""PRO-291 positive invariant: /result carries the validity / psychoemotional
/ mac sections after a completed assessment, and the main RIASEC/BigFive/MI
report still comes back even when a psych-block calculation is forced to blow
up. This is NOT a "does not leak" guard (PRO-282 §3 explicitly wants the
sections visible in the MVP) — it's the isolation + wiring contract.

LLM is monkeypatched off explicitly (same reasoning as
test_result_v2_fallback.py: this dev env has a working key).
"""
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.schemas.result_v2 import ResultResponseV2, ValiditySection
from app.services import (
    assessment_shared,
    consent_service,
    llm_client,
    motivation_pair_service,
    motivation_service,
    report_service,
)


async def _make_assessment(db_session: AsyncSession, age_group: AgeGroup) -> tuple[User, Assessment]:
    user = User(
        email=f"{uuid.uuid4()}@example.com", hashed_password="x", is_active=True, is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    profile = Profile(
        user_id=user.id, name="Тест", age={AgeGroup.junior: 8, AgeGroup.senior: 16}[age_group],
        grade=5, city="Алматы", country="Казахстан", language="ru", age_group=age_group,
    )
    db_session.add(profile)
    await db_session.flush()

    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db_session.add(assessment)
    await db_session.flush()
    return user, assessment


def _force_complete_and_llm_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assessment_shared, "likert_answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "likert_total_questions", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "total_triplets", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_pair_service, "answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_pair_service, "total_pairs", AsyncMock(return_value=1))
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)


async def test_result_carries_the_three_psych_sections(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch)

    response = await report_service.build_report(assessment.id, db_session, viewer=user)

    dumped = response.model_dump()
    # Present as keys (skeleton contract) — `null` until Фазы 1/2/3 ship.
    for section in ("validity", "psychoemotional", "mac"):
        assert section in dumped
        assert dumped[section] is None


async def test_main_report_survives_a_broken_psych_block_calculation(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch)

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("psychoemotional scoring blew up")

    monkeypatch.setattr(report_service, "_build_psychoemotional_section", _boom)

    response = await report_service.build_report(assessment.id, db_session, viewer=user)

    assert isinstance(response, ResultResponseV2)
    assert response.summary  # main report fully intact
    assert response.interest_instrument == "riasec"
    assert len(response.interest_map) == 6
    assert response.psychoemotional is None  # broken block degraded to null
    assert response.validity is None
    assert response.mac is None


async def test_psych_sections_for_is_the_single_visibility_switch(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch)

    async def _stub_validity(*_args, **kwargs):
        return ValiditySection(consent_ok=kwargs.get("consent_ok", False))

    monkeypatch.setattr(report_service, "_build_validity_section", _stub_validity)

    on = await report_service.build_report(assessment.id, db_session, viewer=user)
    assert on.validity is not None

    # Flip the one resolver → section withheld, main report still returned.
    # No cache-bust needed: the base report is cached, psych sections are
    # re-attached on every call.
    monkeypatch.setattr(report_service, "psych_sections_for", lambda *a, **k: False)
    off = await report_service.build_report(assessment.id, db_session, viewer=user)
    assert off.summary
    assert off.validity is None


async def test_consent_ok_flows_from_a_recorded_consent(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch)

    async def _echo_consent(_assessment_id, _db, *, consent_ok):
        return ValiditySection(consent_ok=consent_ok)

    monkeypatch.setattr(report_service, "_build_validity_section", _echo_consent)

    before = await report_service.build_report(assessment.id, db_session, viewer=user)
    assert before.validity is not None and before.validity.consent_ok is False

    await consent_service.record_consent(
        db_session, user_id=user.id, signed_by="Родитель", assessment_id=assessment.id
    )
    after = await report_service.build_report(assessment.id, db_session, viewer=user)
    assert after.validity is not None and after.validity.consent_ok is True
