"""report_service.build_report must not generate (and must not flip status
to `completed`) for an assessment that isn't actually done.

This runs against the shared dev DB (see tests/conftest.py — rollback-
isolated, but real seeded content: ~300 questions, dozens of motivation
pairs/triplets already exist). Required *totals* are global counts
(assessment_shared.likert_total_questions, motivation_service.total_triplets
all count every matching row in the
table, not just this assessment's), so there's no way to seed a small,
literally-complete assessment without also answering every real seeded row.
Instead of fighting that, the completion counters are monkeypatched to
known values — this tests _assert_assessment_complete's gating (Likert,
motivation triplets, Belbin + АСТУР) precisely, without
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
    Question,
    QuestionInstrument,
)
from app.models.user import User
from app.models.user_response import UserResponse
from app.schemas.response import AnswerItem
from app.services import (
    assessment_service,
    assessment_shared,
    llm_client,
    motivation_service,
    report_service,
    riasec_service,
)
from app.services.riasec_service import HOLLAND_ORDER

# Far outside real seed data's order range (~300 real questions) — see
# test_age_matrix_full_flow.py's identical convention.
_SENTINEL_ORDER = 900_300

_SENTINEL_BASE = 960_000
_MAX_ANSWER = 5  # top of the Likert scale — see riasec_service.normalize


async def _make_assessment(db_session: AsyncSession) -> Assessment:
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
        age=16,
        grade=5,
        city="Алматы",
        country="Казахстан",
        language="ru",
        age_group=AgeGroup.senior,
    )
    db_session.add(profile)
    await db_session.flush()

    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db_session.add(assessment)
    await db_session.flush()
    return assessment


async def _answer_all_of_type_at_max(db_session: AsyncSession, assessment: Assessment) -> None:
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
    question_ids = (
        await db_session.execute(
            select(Question.id).where(
                Question.instrument == QuestionInstrument.riasec,
                Question.riasec_type == HollandType.R,
            )
        )
    ).scalars().all()
    assert question_ids, "seeded question bank is missing RIASEC R rows"

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


def _patch_battery(monkeypatch: pytest.MonkeyPatch, *, completed: bool) -> None:
    """Belbin + АСТУР are also required for completion (assessment_shared.
    belbin_and_astur_completed) — every student is routed through both right
    after motivation in the continuous flow (MotivationTripletFlow.tsx), not
    just psychologist-assigned ones. Patched
    the same way the Likert/motivation counters above are: these tests pin
    _assert_assessment_complete's own branching, not belbin_service/
    astur_service's real run-tracking (covered separately)."""
    monkeypatch.setattr(
        assessment_shared, "belbin_and_astur_completed", AsyncMock(return_value=completed)
    )


async def _seed_riasec_dominant(
    db: AsyncSession, assessment: Assessment, profile_id: uuid.UUID, *, dominant: str,
) -> int:
    """Real RIASEC Question rows (one per Holland letter), answered for real
    with `dominant` scored high — riasec_service.strengths_weaknesses()
    deliberately returns [] for a flat/all-zero profile (see its docstring),
    which is what the monkeypatched-completion-counter shortcut alone
    produces. Returns the seeded count, to patch likert_*_count with."""
    answers = []
    for i, letter in enumerate(HOLLAND_ORDER):
        q = Question(
            instrument=QuestionInstrument.riasec, riasec_type=HollandType(letter),
            text={"ru": f"test-completion-gate-riasec-{letter}"},
            order=_SENTINEL_BASE + i,
        )
        db.add(q)
        await db.flush()
        answers.append(AnswerItem(question_id=q.id, value=5 if letter == dominant else 2))
    await assessment_service.submit_answers(assessment.id, answers, profile_id, db)
    return len(answers)


async def test_incomplete_triplet_returns_409_and_does_not_complete(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assessment = await _make_assessment(db_session)
    _patch_likert(monkeypatch, answered=5, total=5)
    _patch_senior_motivation(monkeypatch, answered=0, total=1)  # untouched

    with pytest.raises(HTTPException) as exc_info:
        await report_service.build_report(assessment.id, db_session)

    assert exc_info.value.status_code == 409
    await db_session.refresh(assessment)
    assert assessment.status == AssessmentStatus.in_progress


async def test_likert_and_motivation_done_but_belbin_astur_missing_returns_409(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression for the live bug: a student who finished Likert + motivation
    but hasn't done Belbin/АСТУР yet must not get a "report ready" screen —
    those two are mandatory continuation steps in the flow
    (MotivationTripletFlow.tsx routes every student through both right
    after motivation), not optional extras."""
    assessment = await _make_assessment(db_session)
    _patch_likert(monkeypatch, answered=1, total=1)
    _patch_senior_motivation(monkeypatch, answered=1, total=1)
    _patch_battery(monkeypatch, completed=False)

    with pytest.raises(HTTPException) as exc_info:
        await report_service.build_report(assessment.id, db_session)

    assert exc_info.value.status_code == 409
    await db_session.refresh(assessment)
    assert assessment.status == AssessmentStatus.in_progress
    assert assessment.completed_at is None


async def test_successful_generation_atomically_sets_completion_and_result(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assessment = await _make_assessment(db_session)
    _patch_likert(monkeypatch, answered=1, total=1)
    _patch_senior_motivation(monkeypatch, answered=1, total=1)
    _patch_battery(monkeypatch, completed=True)
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
    assessment = await _make_assessment(db_session)
    await _answer_all_of_type_at_max(db_session, assessment)
    _patch_likert(monkeypatch, answered=1, total=1)
    _patch_senior_motivation(monkeypatch, answered=1, total=1)
    _patch_battery(monkeypatch, completed=True)
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)

    # A tiny, controlled RIASEC signal so the deterministic fallback has real
    # per-type differentiation to build strength-card evidence from — without
    # it every type scores 0% on this assessment's zero real answers and
    # riasec_service.strengths_weaknesses honestly returns no strengths (a
    # deliberate anti-padding guard for a genuinely flat profile, see its own
    # docstring), which isn't what this test is pinning (the report_version=2
    # narrative-service wiring). question_counts is patched to match exactly
    # what's seeded here, not the ~150 real rows already in the dev DB.
    signal_questions = [
        Question(
            instrument=QuestionInstrument.riasec, riasec_type=HollandType.R,
            text={"ru": f"test-riasec-signal-{i}"}, order=_SENTINEL_ORDER + i,
        )
        for i in range(3)
    ]
    db_session.add_all(signal_questions)
    await db_session.flush()
    db_session.add_all(
        UserResponse(assessment_id=assessment.id, question_id=q.id, answer_value=5) for q in signal_questions
    )
    await db_session.flush()
    monkeypatch.setattr(
        riasec_service, "question_counts",
        AsyncMock(return_value={t: (3 if t == "R" else 0) for t in riasec_service.HOLLAND_ORDER}),
    )

    await report_service.build_report(assessment.id, db_session)

    stored = await db_session.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment.id)
    )
    analysis = stored.scalar_one()
    assert analysis.report_version == 2
    assert analysis.strength_cards
    for card in analysis.strength_cards:
        assert set(card.keys()) == {"title", "description"}


async def test_report_has_no_personality_section_when_big_five_was_never_answered(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Big Five retired from the active pool (docs/big-five-retirement.md) —
    a new assessment answers zero Big Five items even though the real
    seeded bank still exists (get_all_questions/get_pairs no longer serve
    it). report_service's compute_bigfive gate must skip the personality/
    thinking-style block entirely rather than compute a fake floor profile
    (bigfive_service.normalize turns "no answers" into a misleading 0% on
    four traits and a fake 100% Emotional Stability)."""
    assessment = await _make_assessment(db_session)
    await _answer_all_of_type_at_max(db_session, assessment)
    _patch_likert(monkeypatch, answered=1, total=1)
    _patch_senior_motivation(monkeypatch, answered=1, total=1)
    _patch_battery(monkeypatch, completed=True)
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)

    response = await report_service.build_report(assessment.id, db_session)

    assert response.personality_notes == []
    assert response.personality_note == ""
    assert response.thinking_style_notes == []

    stored = await db_session.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment.id)
    )
    analysis = stored.scalar_one()
    assert analysis.big_five == {}
    assert analysis.personality_profile == {}
    assert analysis.thinking_style == {}


async def test_report_has_no_personality_section_when_big_five_only_partially_answered(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Transition-window case: a user mid-test at the moment Big Five was
    excluded from the active pool may have answered a handful of items
    under the old serving code before finishing after deploy. A partial
    set must not produce a partial/broken profile — it's all-or-nothing,
    same treatment as a fresh assessment with zero answers."""
    assessment = await _make_assessment(db_session)
    await _answer_all_of_type_at_max(db_session, assessment)
    _patch_likert(monkeypatch, answered=1, total=1)
    _patch_senior_motivation(monkeypatch, answered=1, total=1)
    _patch_battery(monkeypatch, completed=True)
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)

    bf_question_id = (
        await db_session.execute(
            select(Question.id).where(
                Question.instrument == QuestionInstrument.big_five,
            ).limit(1)
        )
    ).scalar_one()
    db_session.add(UserResponse(assessment_id=assessment.id, question_id=bf_question_id, answer_value=4))
    await db_session.flush()

    response = await report_service.build_report(assessment.id, db_session)

    assert response.personality_notes == []
    assert response.personality_note == ""


async def test_report_has_full_personality_section_when_big_five_fully_answered(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Legacy-equivalent case: an assessment that answered every Big Five
    item this tier's real seeded bank has still gets the full "Твой
    характер"/"Стиль мышления" sections computed for real — retirement
    only changes what NEW assessments are served, not what a genuinely
    complete answer set does (covers a user who finished the whole Big
    Five test in the transition window right before deploy)."""
    assessment = await _make_assessment(db_session)
    await _answer_all_of_type_at_max(db_session, assessment)
    _patch_likert(monkeypatch, answered=1, total=1)
    _patch_senior_motivation(monkeypatch, answered=1, total=1)
    _patch_battery(monkeypatch, completed=True)
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)

    bf_question_ids = (
        await db_session.execute(
            select(Question.id).where(
                Question.instrument == QuestionInstrument.big_five,
            )
        )
    ).scalars().all()
    assert bf_question_ids, "seeded question bank is missing Big Five rows for this age tier"
    db_session.add_all([
        UserResponse(assessment_id=assessment.id, question_id=qid, answer_value=4)
        for qid in bf_question_ids
    ])
    await db_session.flush()

    response = await report_service.build_report(assessment.id, db_session)

    assert len(response.personality_notes) == 5
    assert response.personality_note != ""
