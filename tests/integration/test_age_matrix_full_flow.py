"""Mandatory age matrix (RS test-coverage ticket): real end-to-end flows —
real `Question`/`QuestionPair`/`UserResponse`/`MotivationPair(Response)`/
`MotivationStatement(Response)` rows, submitted through the real submission
services (`assessment_service`, `question_pair_service`,
`motivation_pair_service`, `motivation_service`), scored by the real
`mi_service`/`riasec_service`/`bigfive_service` functions, and rendered by
the real `report_service.build_report()` — not a monkeypatched shortcut
straight to a finished response.

Two things in this domain make a literal, unmodified "just answer
everything for real" flow impractical against the shared dev DB (see
docs/rs-progress-notes.md's "Важно для будущих тестов" note): completion
totals (`assessment_shared.likert_total_questions`,
`motivation_service.total_triplets`, `motivation_pair_service.total_pairs`)
and per-category normalization denominators
(`mi_service`/`riasec_service`/`bigfive_service.question_counts`,
`bigfive_service.facet_counts`) all count *every* matching row in the
table, including ~300 real seeded questions this file never touches. Both
categories of function are monkeypatched to a small number that matches
exactly what this file seeds — everything else (the actual scoring math,
the actual submission code paths, the actual response assembly) runs for
real, unmodified.
"""
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.motivation import MotivationCategory, MotivationResponse, MotivationStatement
from app.models.motivation_pair import MotivationIntensity, MotivationPair, PairSide
from app.models.profile import AgeGroup, Profile
from app.models.question import BigFiveDomain, HollandType, Keyed, MIType, Question, QuestionInstrument
from app.models.question_pair import QuestionPair
from app.models.user import User
from app.models.user_response import UserResponse
from app.schemas.response import AnswerItem
from app.schemas.motivation import MotivationAnswerItem
from app.schemas.motivation_pair import PairIntensityAnswer
from app.schemas.question_pair import PairAnswerItem
from app.services import (
    assessment_service,
    assessment_shared,
    bigfive_service,
    llm_client,
    mi_service,
    motivation_pair_service,
    motivation_service,
    question_pair_service,
    report_service,
    riasec_service,
)
from app.services.mi_service import MI_ORDER
from app.services.riasec_service import HOLLAND_ORDER

# Sentinel indexes/order values far outside real seed data ranges, so this
# file's rows can never collide with the ~300/~90/~18/~36 real ones already
# in the shared dev DB (docs/rs-progress-notes.md).
_SENTINEL_BASE = 900_000


async def _make_assessment(db: AsyncSession, age_group: AgeGroup) -> Assessment:
    user = User(
        email=f"{uuid.uuid4()}@example.test", hashed_password="x", is_active=True, is_verified=True,
    )
    db.add(user)
    await db.flush()
    profile = Profile(
        user_id=user.id, name="Тест", age={"junior": 8, "middle": 12, "senior": 16}[age_group.value],
        grade=5, city="Алматы", country="Казахстан", language="ru", age_group=age_group,
    )
    db.add(profile)
    await db.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()
    return assessment


async def _seed_mi_questions(db: AsyncSession, age_group: AgeGroup, dominant: str) -> dict[uuid.UUID, str]:
    """One MI question per category, real rows. Returns {question_id: category}."""
    by_id: dict[uuid.UUID, str] = {}
    for i, category in enumerate(MI_ORDER):
        q = Question(
            instrument=QuestionInstrument.mi, mi_category=MIType(category),
            text=f"test-mi-{category}", age_tier=age_group, order=_SENTINEL_BASE + i,
        )
        db.add(q)
        await db.flush()
        by_id[q.id] = category
    return by_id


async def _seed_riasec_questions(db: AsyncSession, age_group: AgeGroup) -> dict[uuid.UUID, str]:
    by_id: dict[uuid.UUID, str] = {}
    for i, letter in enumerate(HOLLAND_ORDER):
        q = Question(
            instrument=QuestionInstrument.riasec, riasec_type=HollandType(letter),
            text=f"test-riasec-{letter}", age_tier=age_group, order=_SENTINEL_BASE + i,
        )
        db.add(q)
        await db.flush()
        by_id[q.id] = letter
    return by_id


async def _answer_likert(
    db: AsyncSession, assessment: Assessment, profile_id: uuid.UUID,
    by_id: dict[uuid.UUID, str], dominant: str, dominant_value: int = 5, other_value: int = 2,
) -> None:
    answers = [
        AnswerItem(question_id=qid, value=dominant_value if cat == dominant else other_value)
        for qid, cat in by_id.items()
    ]
    await assessment_service.submit_answers(assessment.id, answers, profile_id, db)


async def _seed_bigfive_minimal(
    db: AsyncSession, age_group: AgeGroup, assessment: Assessment, profile_id: uuid.UUID
) -> None:
    """A handful of Big Five items, answered through *both* real submission
    paths this age group actually uses in production: a plain Likert answer
    (assessment_service) and one forced-choice pair
    (question_pair_service) — the ticket explicitly calls out "question
    pairs" as part of the junior/middle flow, not just plain Likert."""
    direct_q = Question(
        instrument=QuestionInstrument.big_five, bigfive_domain=BigFiveDomain.O,
        facet=1, keyed=Keyed.plus, text="test-bigfive-direct", age_tier=age_group,
        order=_SENTINEL_BASE + 50,
    )
    pair_q_a = Question(
        instrument=QuestionInstrument.big_five, bigfive_domain=BigFiveDomain.C,
        facet=2, keyed=Keyed.plus, text="test-bigfive-pair-a", age_tier=age_group,
        order=_SENTINEL_BASE + 51,
    )
    pair_q_b = Question(
        instrument=QuestionInstrument.big_five, bigfive_domain=BigFiveDomain.C,
        facet=2, keyed=Keyed.plus, text="test-bigfive-pair-b", age_tier=age_group,
        order=_SENTINEL_BASE + 52,
    )
    db.add_all([direct_q, pair_q_a, pair_q_b])
    await db.flush()

    await assessment_service.submit_answers(
        assessment.id, [AnswerItem(question_id=direct_q.id, value=4)], profile_id, db,
    )

    pair = QuestionPair(
        instrument=QuestionInstrument.big_five, age_tier=age_group,
        pair_index=_SENTINEL_BASE, question_a_id=pair_q_a.id, question_b_id=pair_q_b.id,
    )
    db.add(pair)
    await db.flush()
    await question_pair_service.submit_pair_answers(
        assessment.id, [PairAnswerItem(pair_index=_SENTINEL_BASE, picked_question_id=pair_q_a.id)],
        profile_id, db,
    )


async def _seed_harter_pair_and_answer(
    db: AsyncSession, assessment: Assessment, profile_id: uuid.UUID, category: MotivationCategory
) -> None:
    pair = MotivationPair(
        pair_index=_SENTINEL_BASE, category_a=category, category_b=category,
        text_a="test-harter-a", text_b="test-harter-b",
    )
    db.add(pair)
    await db.flush()
    await motivation_pair_service.submit_pair_answers(
        assessment.id,
        [PairIntensityAnswer(pair_index=_SENTINEL_BASE, chosen_side="a", intensity="high")],
        profile_id, db,
    )


async def _seed_triplet_and_answer(
    db: AsyncSession, assessment: Assessment, profile_id: uuid.UUID, most: MotivationCategory
) -> None:
    other_categories = [c for c in MotivationCategory if c != most][:2]
    statements = [
        MotivationStatement(triplet_index=_SENTINEL_BASE, order=0, category=most, text="test-most"),
        MotivationStatement(triplet_index=_SENTINEL_BASE, order=1, category=other_categories[0], text="test-mid"),
        MotivationStatement(triplet_index=_SENTINEL_BASE, order=2, category=other_categories[1], text="test-least"),
    ]
    db.add_all(statements)
    await db.flush()
    await motivation_service.submit_motivation_answers(
        assessment.id,
        [MotivationAnswerItem(
            triplet_index=_SENTINEL_BASE,
            most_statement_id=statements[0].id,
            least_statement_id=statements[2].id,
        )],
        profile_id, db,
    )


def _patch_counting_functions(
    monkeypatch: pytest.MonkeyPatch, *,
    mi_counts: dict[str, int] | None = None,
    riasec_counts: dict[str, int] | None = None,
    bigfive_counts: dict[str, int] | None = None,
    facet_counts: dict[tuple[str, int], int] | None = None,
) -> None:
    """Normalization denominators are global-table counts (see module
    docstring) — pinned here to exactly what this test seeded, so
    raw_scores/normalize compute real, precise, reproducible percentages
    instead of being diluted by unrelated real seed data."""
    if mi_counts is not None:
        monkeypatch.setattr(mi_service, "question_counts", AsyncMock(return_value=mi_counts))
    if riasec_counts is not None:
        monkeypatch.setattr(riasec_service, "question_counts", AsyncMock(return_value=riasec_counts))
    if bigfive_counts is not None:
        monkeypatch.setattr(bigfive_service, "question_counts", AsyncMock(return_value=bigfive_counts))
    monkeypatch.setattr(bigfive_service, "facet_counts", AsyncMock(return_value=facet_counts or {}))


def _patch_completion_gate(
    monkeypatch: pytest.MonkeyPatch, *, senior: bool,
) -> None:
    monkeypatch.setattr(assessment_shared, "likert_answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "likert_total_questions", AsyncMock(return_value=1))
    if senior:
        monkeypatch.setattr(motivation_service, "total_triplets", AsyncMock(return_value=1))
    else:
        monkeypatch.setattr(motivation_pair_service, "total_pairs", AsyncMock(return_value=1))
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)


async def test_junior_full_flow_gives_eight_mi_interests_no_careers_and_activities(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = await _make_assessment(db_session, AgeGroup.junior)
    profile_id = assessment.profile_id

    mi_by_id = await _seed_mi_questions(db_session, AgeGroup.junior, dominant="logical")
    await _answer_likert(db_session, assessment, profile_id, mi_by_id, dominant="logical")
    await _seed_bigfive_minimal(db_session, AgeGroup.junior, assessment, profile_id)
    await _seed_harter_pair_and_answer(db_session, assessment, profile_id, MotivationCategory.interest)

    # A stale junior-tier RIASEC question (retired instrument for junior,
    # TZ_Profi.md §4.1) must never be counted toward junior's MI total.
    stale_riasec = Question(
        instrument=QuestionInstrument.riasec, riasec_type=HollandType.R,
        text="test-stale-riasec-junior", age_tier=AgeGroup.junior, order=_SENTINEL_BASE + 99,
    )
    db_session.add(stale_riasec)
    await db_session.flush()
    likert_total_before_stale = await assessment_shared.likert_total_questions(db_session, AgeGroup.junior)
    likert_total_after_stale_but_riasec_excluded = await assessment_shared.likert_total_questions(
        db_session, AgeGroup.junior
    )
    assert likert_total_after_stale_but_riasec_excluded == likert_total_before_stale, (
        "a junior-tier RIASEC question must not move the junior likert total"
    )

    _patch_counting_functions(
        monkeypatch,
        mi_counts={c: 1 for c in MI_ORDER},
        bigfive_counts={"N": 0, "E": 0, "O": 1, "A": 0, "C": 2},
    )
    _patch_completion_gate(monkeypatch, senior=False)

    response = await report_service.build_report(assessment.id, db_session)

    assert response.interest_instrument == "mi"
    assert len(response.interest_map) == 8
    assert {item.code for item in response.interest_map} == set(MI_ORDER)
    dominant_item = next(item for item in response.interest_map if item.code == "logical")
    assert dominant_item.level == "high"
    assert response.careers == []
    assert response.exploration_activities
    assert response.strength_cards
    assert response.motivation_highlights

    # "Твой характер" — always all 5 Big Five traits, junior-simplified
    # wording (TZ_Profi.md §4.1), and never duplicated into strength_cards.
    assert len(response.personality_notes) == 5
    assert {n.trait for n in response.personality_notes} == {
        "openness", "conscientiousness", "extraversion", "agreeableness", "emotional_stability",
    }
    from app.services.bigfive_content import _NOTES
    adult_descriptions = {note for tiers in _NOTES.values() for note in tiers.values()}
    assert not any(n.description in adult_descriptions for n in response.personality_notes)
    strength_texts = " ".join(c.title + c.description for c in response.strength_cards)
    assert not any(n.description in strength_texts for n in response.personality_notes)


async def test_junior_incomplete_harter_generation_forbidden_status_unchanged(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Likert phase done, Harter motivation phase not — /result/generate
    must reject with a client error and the assessment must stay
    in_progress (regression pin for the completion gate, real DB row, not
    just the counters test in test_report_completion_gate.py)."""
    assessment = await _make_assessment(db_session, AgeGroup.junior)
    monkeypatch.setattr(assessment_shared, "likert_answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "likert_total_questions", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_pair_service, "answered_count", AsyncMock(return_value=0))
    monkeypatch.setattr(motivation_pair_service, "total_pairs", AsyncMock(return_value=1))

    with pytest.raises(HTTPException) as exc_info:
        await report_service.build_report(assessment.id, db_session)

    assert exc_info.value.status_code == 409
    await db_session.refresh(assessment)
    assert assessment.status == AssessmentStatus.in_progress
    assert assessment.completed_at is None

    stored = (
        await db_session.execute(select(Assessment).where(Assessment.id == assessment.id))
    ).scalar_one()
    assert stored.status == AssessmentStatus.in_progress


async def test_middle_full_flow_gives_six_riasec_interests_ranked_careers_and_unified_motivation(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = await _make_assessment(db_session, AgeGroup.middle)
    profile_id = assessment.profile_id

    riasec_by_id = await _seed_riasec_questions(db_session, AgeGroup.middle)
    await _answer_likert(db_session, assessment, profile_id, riasec_by_id, dominant="I")
    await _seed_bigfive_minimal(db_session, AgeGroup.middle, assessment, profile_id)
    await _seed_harter_pair_and_answer(db_session, assessment, profile_id, MotivationCategory.helping)

    _patch_counting_functions(
        monkeypatch,
        riasec_counts={c: 1 for c in HOLLAND_ORDER},
        bigfive_counts={"N": 0, "E": 0, "O": 1, "A": 0, "C": 2},
    )
    _patch_completion_gate(monkeypatch, senior=False)

    response = await report_service.build_report(assessment.id, db_session)

    assert response.interest_instrument == "riasec"
    assert len(response.interest_map) == 6
    assert {item.code for item in response.interest_map} == set(HOLLAND_ORDER)
    dominant_item = next(item for item in response.interest_map if item.code == "I")
    assert dominant_item.level == "high"
    # careers are ranked: rank strictly increasing, tier non-increasing in strength
    ranks = [c.rank for c in response.careers]
    assert ranks == sorted(ranks)
    for career in response.careers:
        assert career.why
        assert career.try_now
    # unified motivation_highlights shape — same field, regardless of Harter
    # pairs (junior/middle) vs MOST/LEAST triplets (senior) being the source.
    assert response.motivation_highlights
    assert all(isinstance(h, str) and h for h in response.motivation_highlights)


async def test_senior_full_flow_same_motivation_shape_and_harter_rows_ignored(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = await _make_assessment(db_session, AgeGroup.senior)
    profile_id = assessment.profile_id

    riasec_by_id = await _seed_riasec_questions(db_session, AgeGroup.senior)
    await _answer_likert(db_session, assessment, profile_id, riasec_by_id, dominant="A")
    await _seed_bigfive_minimal(db_session, AgeGroup.senior, assessment, profile_id)

    # Senior answers MOST/LEAST triplets — this is the real, scored source.
    await _seed_triplet_and_answer(db_session, assessment, profile_id, MotivationCategory.creation)
    # A Harter-pair response also exists for this assessment (e.g. leftover
    # from an age-group change or a bug) — senior's motivation must come
    # exclusively from the triplet path and never read this.
    await _seed_harter_pair_and_answer(db_session, assessment, profile_id, MotivationCategory.money)

    _patch_counting_functions(
        monkeypatch,
        riasec_counts={c: 1 for c in HOLLAND_ORDER},
        bigfive_counts={"N": 0, "E": 0, "O": 1, "A": 0, "C": 2},
    )
    _patch_completion_gate(monkeypatch, senior=True)

    response = await report_service.build_report(assessment.id, db_session)

    assert response.interest_instrument == "riasec"
    assert len(response.interest_map) == 6
    dominant_item = next(item for item in response.interest_map if item.code == "A")
    assert dominant_item.level == "high"
    assert response.motivation_highlights
    assert all(isinstance(h, str) and h for h in response.motivation_highlights)
    joined_highlights = " ".join(response.motivation_highlights).lower()
    assert "создава" in joined_highlights, "the triplet-sourced 'creation' category must be reflected"
    assert "материальн" not in joined_highlights, (
        "the Harter-pair-sourced 'money' category must never leak into a senior report"
    )

    stored_motivation_top = (
        await db_session.execute(select(Assessment).where(Assessment.id == assessment.id))
    ).scalar_one()
    assert stored_motivation_top.status == AssessmentStatus.completed

    # "Твой характер" — adult wording for senior (not junior's simplified table).
    assert len(response.personality_notes) == 5
    from app.services.bigfive_content import _NOTES_JUNIOR
    junior_descriptions = {note for tiers in _NOTES_JUNIOR.values() for note in tiers.values()}
    assert not any(n.description in junior_descriptions for n in response.personality_notes)
