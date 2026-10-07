"""Full assessment flow (RS test-coverage ticket): real end-to-end —
real `Question`/`QuestionPair`/`UserResponse`/`MotivationStatement(Response)`
rows, submitted through the real submission services
(`assessment_service`, `question_pair_service`, `motivation_service`),
scored by the real `riasec_service`/`bigfive_service` functions, and rendered by
the real `report_service.build_report()` — not a monkeypatched shortcut
straight to a finished response.

Two things in this domain make a literal, unmodified "just answer
everything for real" flow impractical against the shared dev DB (see
docs/rs-progress-notes.md's "Важно для будущих тестов" note): completion
totals (`assessment_shared.likert_total_questions`,
`motivation_service.total_triplets`)
and per-category normalization denominators
(`riasec_service`/`bigfive_service.question_counts`,
`bigfive_service.facet_counts`) all count *every* matching row in the
table, including ~300 real seeded questions this file never touches. Both
categories of function are monkeypatched to a small number that matches
exactly what this file seeds — everything else (the actual scoring math,
the actual submission code paths, the actual response assembly) runs for
real, unmodified.

One battery for everyone (14-18, PRO-425): there are no age tiers, MI or
Harter pairs any more, so a single flow covers the whole matrix.
"""
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.motivation import MotivationCategory, MotivationResponse, MotivationStatement
from app.models.profile import AgeGroup, Profile
from app.models.question import BigFiveDomain, HollandType, Keyed, Question, QuestionInstrument
from app.models.question_pair import QuestionPair
from app.models.user import User
from app.models.user_response import UserResponse
from app.schemas.response import AnswerItem
from app.schemas.motivation import MotivationAnswerItem
from app.schemas.question_pair import PairAnswerItem
from app.services import (
    assessment_service,
    assessment_shared,
    bigfive_service,
    llm_client,
    motivation_service,
    question_pair_service,
    report_service,
    riasec_service,
)
from app.services.riasec_service import HOLLAND_ORDER

# Sentinel indexes/order values far outside real seed data ranges, so this
# file's rows can never collide with the ~300/~90/~18/~36 real ones already
# in the shared dev DB (docs/rs-progress-notes.md).
_SENTINEL_BASE = 900_000


async def _make_assessment(db: AsyncSession) -> Assessment:
    user = User(
        email=f"{uuid.uuid4()}@example.test", hashed_password="x", is_active=True, is_verified=True,
    )
    db.add(user)
    await db.flush()
    profile = Profile(
        user_id=user.id, name="Тест", age=16,
        grade=10, city="Алматы", country="Казахстан", language="ru", age_group=AgeGroup.senior,
    )
    db.add(profile)
    await db.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()
    return assessment


async def _seed_riasec_questions(db: AsyncSession) -> dict[uuid.UUID, str]:
    by_id: dict[uuid.UUID, str] = {}
    for i, letter in enumerate(HOLLAND_ORDER):
        q = Question(
            instrument=QuestionInstrument.riasec, riasec_type=HollandType(letter),
            text={"ru": f"test-riasec-{letter}"}, order=_SENTINEL_BASE + i,
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
    db: AsyncSession, assessment: Assessment, profile_id: uuid.UUID
) -> None:
    """A handful of Big Five items, answered through *both* real submission
    paths: a plain Likert answer (assessment_service) and one forced-choice
    pair (question_pair_service) — a picked pair is scored through the same
    UserResponse path as Likert."""
    direct_q = Question(
        instrument=QuestionInstrument.big_five, bigfive_domain=BigFiveDomain.O,
        facet=1, keyed=Keyed.plus, text={"ru": "test-bigfive-direct"},
        order=_SENTINEL_BASE + 50,
    )
    pair_q_a = Question(
        instrument=QuestionInstrument.big_five, bigfive_domain=BigFiveDomain.C,
        facet=2, keyed=Keyed.plus, text={"ru": "test-bigfive-pair-a"},
        order=_SENTINEL_BASE + 51,
    )
    pair_q_b = Question(
        instrument=QuestionInstrument.big_five, bigfive_domain=BigFiveDomain.C,
        facet=2, keyed=Keyed.plus, text={"ru": "test-bigfive-pair-b"},
        order=_SENTINEL_BASE + 52,
    )
    db.add_all([direct_q, pair_q_a, pair_q_b])
    await db.flush()

    await assessment_service.submit_answers(
        assessment.id, [AnswerItem(question_id=direct_q.id, value=4)], profile_id, db,
    )

    pair = QuestionPair(
        instrument=QuestionInstrument.big_five,
        pair_index=_SENTINEL_BASE, question_a_id=pair_q_a.id, question_b_id=pair_q_b.id,
    )
    db.add(pair)
    await db.flush()
    await question_pair_service.submit_pair_answers(
        assessment.id, [PairAnswerItem(pair_index=_SENTINEL_BASE, picked_question_id=pair_q_a.id)],
        profile_id, db,
    )


async def _seed_triplet_and_answer(
    db: AsyncSession, assessment: Assessment, profile_id: uuid.UUID, most: MotivationCategory
) -> None:
    other_categories = [c for c in MotivationCategory if c != most][:2]
    statements = [
        MotivationStatement(triplet_index=_SENTINEL_BASE, order=0, category=most, text={"ru": "test-most"}),
        MotivationStatement(triplet_index=_SENTINEL_BASE, order=1, category=other_categories[0], text={"ru": "test-mid"}),
        MotivationStatement(triplet_index=_SENTINEL_BASE, order=2, category=other_categories[1], text={"ru": "test-least"}),
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
    riasec_counts: dict[str, int] | None = None,
    bigfive_counts: dict[str, int] | None = None,
    facet_counts: dict[tuple[str, int], int] | None = None,
) -> None:
    """Normalization denominators are global-table counts (see module
    docstring) — pinned here to exactly what this test seeded, so
    raw_scores/normalize compute real, precise, reproducible percentages
    instead of being diluted by unrelated real seed data."""
    if riasec_counts is not None:
        monkeypatch.setattr(riasec_service, "question_counts", AsyncMock(return_value=riasec_counts))
    if bigfive_counts is not None:
        monkeypatch.setattr(bigfive_service, "question_counts", AsyncMock(return_value=bigfive_counts))
    monkeypatch.setattr(bigfive_service, "facet_counts", AsyncMock(return_value=facet_counts or {}))
    # Neutralize the acquiescence correction: balanced keying + a midpoint
    # grand mean make `_acquiescence_shift` exactly 0, so raw_scores/normalize
    # stay the clean reproducible percentages this test reasons about (the
    # correction itself is covered by tests/unit/test_bigfive_service.py).
    monkeypatch.setattr(
        bigfive_service, "keying_counts",
        AsyncMock(return_value={d: (0, 0) for d in bigfive_service.BIGFIVE_ORDER}),
    )
    monkeypatch.setattr(bigfive_service, "facet_keying_counts", AsyncMock(return_value={}))
    monkeypatch.setattr(bigfive_service, "grand_mean", AsyncMock(return_value=3.0))


def _patch_completion_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assessment_shared, "likert_answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "likert_total_questions", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "total_triplets", AsyncMock(return_value=1))
    # Belbin + АСТУР are also required for completion now (assessment_shared.
    # belbin_and_astur_completed) — this file's flows never touch either, so
    # without this they'd 409 at the completion gate before ever reaching the
    # scoring/report-assembly code this test actually exercises.
    monkeypatch.setattr(assessment_shared, "belbin_and_astur_completed", AsyncMock(return_value=True))
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)


async def test_full_flow_gives_six_riasec_interests_ranked_careers_and_motivation(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = await _make_assessment(db_session)
    profile_id = assessment.profile_id

    riasec_by_id = await _seed_riasec_questions(db_session)
    await _answer_likert(db_session, assessment, profile_id, riasec_by_id, dominant="A")

    await _seed_triplet_and_answer(db_session, assessment, profile_id, MotivationCategory.creation)

    _patch_counting_functions(
        monkeypatch,
        riasec_counts={c: 1 for c in HOLLAND_ORDER},
        bigfive_counts={"N": 0, "E": 0, "O": 1, "A": 0, "C": 2},
    )
    _patch_completion_gate(monkeypatch)

    response = await report_service.build_report(assessment.id, db_session)

    assert response.interest_instrument == "riasec"
    assert len(response.interest_map) == 6
    assert {item.code for item in response.interest_map} == set(HOLLAND_ORDER)
    dominant_item = next(item for item in response.interest_map if item.code == "A")
    assert dominant_item.level == "high"
    assert response.motivation_highlights
    assert all(isinstance(h, str) and h for h in response.motivation_highlights)
    joined_highlights = " ".join(response.motivation_highlights).lower()
    assert "создава" in joined_highlights, "the triplet-sourced 'creation' category must be reflected"

    stored_motivation_top = (
        await db_session.execute(select(Assessment).where(Assessment.id == assessment.id))
    ).scalar_one()
    assert stored_motivation_top.status == AssessmentStatus.completed

    ranks = [c.rank for c in response.careers]
    assert ranks == sorted(ranks)
    for career in response.careers:
        assert career.why
        assert career.try_now

    # New attempts do not expose the retired Big Five-derived sections.
    assert response.personality_notes == []
    assert response.personality_note == ""
    assert response.thinking_style_notes == []
