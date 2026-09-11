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
from app.services import assessment_shared, llm_client, motivation_pair_service, motivation_service, report_service
from app.services.age_tiers import visible_tiers

_AGE_SAMPLE = {AgeGroup.junior: 8, AgeGroup.middle: 12, AgeGroup.senior: 16}
_MAX_ANSWER = 5  # top of the Likert scale — see riasec_service.normalize


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


async def _answer_all_of_type_at_max(
    db_session: AsyncSession, assessment: Assessment, age_group: AgeGroup
) -> None:
    """Give the assessment one genuinely strong interest type by answering
    every question of that type with the maximum value.

    Scores are normalized against the maximum possible for the type
    (riasec_service.normalize: raw / (count * 5)), and
    strengths_weaknesses() refuses to promote anything below
    LEVEL_MEDIUM_MIN — so an assessment with no responses at all scores 0
    everywhere and correctly yields NO strengths, hence no strength_cards.
    That floor is deliberate (it stops a floor-level type from being cited
    as evidence), so a test asserting a populated report has to supply a
    real signal rather than rely on the old blind top-3 behaviour.

    Only the counters are monkeypatched to make the assessment "complete";
    these rows are real answers, so the resulting score is real too."""
    if age_group == AgeGroup.junior:
        type_filter = (
            Question.instrument == QuestionInstrument.mi,
            Question.mi_category == MIType.logical,
        )
    else:
        type_filter = (
            Question.instrument == QuestionInstrument.riasec,
            Question.riasec_type == HollandType.R,
        )

    question_ids = (
        await db_session.execute(
            select(Question.id).where(
                *type_filter, Question.age_tier.in_(visible_tiers(age_group))
            )
        )
    ).scalars().all()
    assert question_ids, "seeded question bank is missing rows for this instrument/age tier"

    db_session.add_all(
        [
            UserResponse(assessment_id=assessment.id, question_id=qid, answer_value=_MAX_ANSWER)
            for qid in question_ids
        ]
    )
    await db_session.flush()



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


async def test_disabled_llm_returns_full_v2_form_for_senior(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assessment = await _make_assessment(db_session, AgeGroup.senior)
    await _answer_all_of_type_at_max(db_session, assessment, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch, senior=True)

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
    # letter with this profile's top code — but every field must still be
    # well-formed either way.
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
    await _answer_all_of_type_at_max(db_session, assessment, AgeGroup.junior)
    _force_complete_and_llm_disabled(monkeypatch, senior=False)

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
