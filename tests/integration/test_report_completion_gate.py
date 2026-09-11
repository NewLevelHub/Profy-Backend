"""report_service.build_report must not generate (and must not flip status
to `completed`) for an assessment that isn't actually done.

This runs against the shared dev DB (see tests/conftest.py — rollback-
isolated, but real seeded content: ~300 questions, dozens of motivation
pairs/triplets already exist). Required *totals* are global counts
(assessment_shared.likert_total_questions, motivation_service.total_triplets,
motivation_pair_service.total_pairs all count every matching row in the
table, not just this assessment's), so there's no way to seed a small,
literally-complete assessment without also answering every real seeded row.
Instead of fighting that, the completion counters are monkeypatched to
known values — this tests _assert_assessment_complete's age-branching (does
it consult the right counters for the right age group) precisely, without
depending on exactly what happens to be seeded."""

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.profile import AgeGroup, Profile
from app.models.question import (
    BigFiveDomain,
    HollandType,
    MIType,
    Question,
    QuestionInstrument,
)
from app.models.user_response import UserResponse
from app.models.user import User
from app.services.age_tiers import visible_tiers
from app.services import (
    assessment_shared,
    llm_client,
    motivation_pair_service,
    motivation_service,
    report_service,
)

_AGE_SAMPLE = {AgeGroup.junior: 8, AgeGroup.middle: 12, AgeGroup.senior: 16}
_MAX_ANSWER = 5  # top of the Likert scale — see riasec_service.normalize


async def _make_assessment(db_session: AsyncSession, age_group: AgeGroup) -> Assessment:
    user = User(
        email=f"{uuid.uuid4()}@example.test",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    profile = Profile(
        user_id=user.id,
        name="Тест",
        age=_AGE_SAMPLE[age_group],
        grade=5,
        city="Алматы",
        country="Казахстан",
        language="ru",
        age_group=age_group,
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



def _patch_likert(monkeypatch: pytest.MonkeyPatch, *, answered: int, total: int) -> None:
    monkeypatch.setattr(
        assessment_shared, "likert_answered_count", AsyncMock(return_value=answered)
    )
    monkeypatch.setattr(assessment_shared, "likert_total_questions", AsyncMock(return_value=total))


def _patch_senior_motivation(monkeypatch: pytest.MonkeyPatch, *, answered: int, total: int) -> None:
    monkeypatch.setattr(motivation_service, "answered_count", AsyncMock(return_value=answered))
    monkeypatch.setattr(motivation_service, "total_triplets", AsyncMock(return_value=total))


def _patch_pair_motivation(monkeypatch: pytest.MonkeyPatch, *, answered: int, total: int) -> None:
    monkeypatch.setattr(motivation_pair_service, "answered_count", AsyncMock(return_value=answered))
    monkeypatch.setattr(motivation_pair_service, "total_pairs", AsyncMock(return_value=total))


async def test_junior_incomplete_harter_returns_409_and_does_not_complete(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assessment = await _make_assessment(db_session, AgeGroup.junior)
    _patch_likert(monkeypatch, answered=5, total=5)  # Likert phase fully done
    _patch_pair_motivation(monkeypatch, answered=1, total=2)  # Harter pairs incomplete
    # Senior's counter must not even be consulted for a junior assessment.
    senior_mot = AsyncMock(side_effect=AssertionError("senior triplet counter used for junior"))
    monkeypatch.setattr(motivation_service, "answered_count", senior_mot)

    with pytest.raises(HTTPException) as exc_info:
        await report_service.build_report(assessment.id, db_session)

    assert exc_info.value.status_code == 409
    await db_session.refresh(assessment)
    assert assessment.status == AssessmentStatus.in_progress
    assert assessment.completed_at is None
    senior_mot.assert_not_called()


async def test_middle_incomplete_harter_returns_409_and_does_not_complete(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assessment = await _make_assessment(db_session, AgeGroup.middle)
    _patch_likert(monkeypatch, answered=5, total=5)
    _patch_pair_motivation(monkeypatch, answered=0, total=1)  # untouched

    with pytest.raises(HTTPException) as exc_info:
        await report_service.build_report(assessment.id, db_session)

    assert exc_info.value.status_code == 409
    await db_session.refresh(assessment)
    assert assessment.status == AssessmentStatus.in_progress


async def test_senior_incomplete_triplet_returns_409_and_does_not_complete(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assessment = await _make_assessment(db_session, AgeGroup.senior)
    _patch_likert(monkeypatch, answered=5, total=5)
    _patch_senior_motivation(monkeypatch, answered=0, total=1)  # untouched
    # Junior/middle's counter must not be consulted for a senior assessment.
    pair_mot = AsyncMock(side_effect=AssertionError("Harter pair counter used for senior"))
    monkeypatch.setattr(motivation_pair_service, "answered_count", pair_mot)

    with pytest.raises(HTTPException) as exc_info:
        await report_service.build_report(assessment.id, db_session)

    assert exc_info.value.status_code == 409
    await db_session.refresh(assessment)
    assert assessment.status == AssessmentStatus.in_progress
    pair_mot.assert_not_called()


async def test_junior_likert_total_excludes_stale_riasec_but_counts_mi(
    db_session: AsyncSession,
) -> None:
    """Not an absolute-count assertion (the real dev DB already has ~300
    seeded questions) — a delta: adding a junior-tier RIASEC row must not
    move the junior Likert total, adding a junior-tier MI row must."""
    before = await assessment_shared.likert_total_questions(db_session, AgeGroup.junior)

    from app.models.question import HollandType
    stale_riasec_q = Question(
        instrument=QuestionInstrument.riasec, riasec_type=HollandType.R,
        text="retired", age_tier=AgeGroup.junior,
    )
    db_session.add(stale_riasec_q)
    await db_session.flush()
    after_riasec = await assessment_shared.likert_total_questions(db_session, AgeGroup.junior)
    assert after_riasec == before, "junior total must not count a RIASEC-instrument row"

    mi_q = Question(
        instrument=QuestionInstrument.mi, mi_category=MIType.logical,
        text="mi", age_tier=AgeGroup.junior,
    )
    db_session.add(mi_q)
    await db_session.flush()
    after_mi = await assessment_shared.likert_total_questions(db_session, AgeGroup.junior)
    assert after_mi == before + 1, "junior total must count an MI-instrument row"


async def test_successful_generation_atomically_sets_completion_and_result(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assessment = await _make_assessment(db_session, AgeGroup.senior)
    _patch_likert(monkeypatch, answered=1, total=1)
    _patch_senior_motivation(monkeypatch, answered=1, total=1)
    # This dev env actually has a working LLM key (LLM_ENABLED=true) — force
    # it off so this test is a fast, deterministic fallback run, not an
    # accidental real API call on every suite run.
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)

    response = await report_service.build_report(assessment.id, db_session)

    assert response.summary

    await db_session.refresh(assessment)
    assert assessment.status == AssessmentStatus.completed
    assert assessment.completed_at is not None

    stored = await db_session.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment.id)
    )
    assert stored.scalar_one_or_none() is not None


async def test_successful_generation_populates_v2_narrative_fields(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """report_service.build_report now calls report_narrative_service under
    the hood (docs/rs-progress-notes.md) — this pins that wiring: a fresh
    report must land with report_version=2 and a non-empty strength_cards
    list, not the old report_version=1/empty-list default. LLM is forced
    off (see comment in the previous test) so this exercises the
    deterministic fallback builder, not a real model call."""
    assessment = await _make_assessment(db_session, AgeGroup.senior)
    await _answer_all_of_type_at_max(db_session, assessment, AgeGroup.senior)
    _patch_likert(monkeypatch, answered=1, total=1)
    _patch_senior_motivation(monkeypatch, answered=1, total=1)
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)

    await report_service.build_report(assessment.id, db_session)

    stored = await db_session.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment.id)
    )
    analysis = stored.scalar_one()
    assert analysis.report_version == 2
    assert analysis.strength_cards
    for card in analysis.strength_cards:
        assert set(card.keys()) == {"title", "description"}
