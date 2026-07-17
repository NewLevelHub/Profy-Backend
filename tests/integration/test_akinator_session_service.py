import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.akinator_question import AkinatorQuestion
from app.models.assessment import Assessment, AssessmentGoal
from app.models.assessment_session import SessionStatus
from app.models.direction import Direction
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import akinator_session_service, assessment_session_service
from app.services.akinator_engine import match_score
from scripts.seed_akinator_content import seed_professions, seed_questions, seed_sections


async def _make_assessment(db: AsyncSession) -> Assessment:
    user = User(email=f"{uuid.uuid4()}@test.local", hashed_password="x")
    db.add(user)
    await db.flush()

    profile = Profile(
        user_id=user.id, name="Test Student", age=16, grade=10,
        city="Test City", country="Test Country", language="ru",
        age_group=AgeGroup.senior,
    )
    db.add(profile)
    await db.flush()

    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()
    return assessment


async def _ensure_seeded(db: AsyncSession) -> None:
    """Idempotent — safe whether or not scripts/seed_akinator_content.py was
    already run for real against this DB."""
    section_ids, *_ = await seed_sections(db)
    await seed_professions(db, section_ids)
    await seed_questions(db)
    await db.flush()


async def test_full_session_reveals_within_expected_question_range(db_session: AsyncSession):
    """AC1: a full session on the seeded content bank reveals within a
    bounded, non-trivial number of questions."""
    await _ensure_seeded(db_session)
    assessment = await _make_assessment(db_session)

    result = await db_session.execute(select(Direction).where(Direction.slug == "surgeon"))
    target_profile = result.scalar_one().profile

    turn = await akinator_session_service.start_session(
        assessment.id, AgeGroup.senior, db_session
    )
    assert turn.decision.status == "continue"
    assert turn.next_question is not None
    assert turn.next_question.depth <= 1
    assert turn.next_question.kind == "direct"

    questions_asked = 0
    max_turns = settings.AKINATOR_CEILING_SENIOR + 1  # hard upper bound, never loops forever

    while turn.decision.status == "continue":
        question = turn.next_question
        assert question is not None

        best_option = max(
            range(len(question.options)),
            key=lambda i: match_score(question.options[i].get("axis_weights", {}), target_profile),
        )
        turn = await akinator_session_service.submit_answer(
            assessment.id, question.id, best_option, AgeGroup.senior, db_session
        )
        questions_asked += 1
        assert questions_asked <= max_turns, "session never converged within the age ceiling"

    # Doesn't assert *which* profession/cluster wins: the seeded profiles are
    # an explicitly uncalibrated draft (see profi_full_catalog.md), so a
    # consistent "favor surgeon" answering strategy can still legitimately
    # tip toward another leaf once questions stray outside medicine. AC1 is
    # about the mechanism (state → math → content → reveal) terminating
    # correctly and promptly, not about calibration accuracy.
    assert turn.decision.status in ("reveal_single", "reveal_cluster")
    assert 1 <= questions_asked <= settings.AKINATOR_CEILING_SENIOR
    if turn.decision.status == "reveal_single":
        assert len(turn.decision.leaves) == 1
    else:
        assert 1 <= len(turn.decision.leaves) <= settings.AKINATOR_STOP_CLUSTER_K

    assert turn.session.status in (SessionStatus.converged_single, SessionStatus.converged_cluster,
                                    SessionStatus.exhausted_ceiling)


async def test_resubmitting_an_answered_question_is_rejected_and_belief_unchanged(
    db_session: AsyncSession,
):
    """AC2: answering the same question twice is rejected and doesn't double-apply belief."""
    await _ensure_seeded(db_session)
    assessment = await _make_assessment(db_session)

    turn = await akinator_session_service.start_session(
        assessment.id, AgeGroup.senior, db_session
    )
    question = turn.next_question
    assert question is not None

    turn = await akinator_session_service.submit_answer(
        assessment.id, question.id, 0, AgeGroup.senior, db_session
    )
    belief_after_first_answer = dict(turn.session.belief)
    step_after_first_answer = turn.session.step

    with pytest.raises(ValueError):
        await akinator_session_service.submit_answer(
            assessment.id, question.id, 0, AgeGroup.senior, db_session
        )

    assert turn.session.belief == belief_after_first_answer
    assert turn.session.step == step_after_first_answer


async def test_reject_leaves_drops_every_shown_leaf_in_one_call(db_session: AsyncSession):
    """The "none of these fit" footer action rejects every leaf on the
    current reveal at once, then re-derives the turn same as a single reject."""
    await _ensure_seeded(db_session)
    assessment = await _make_assessment(db_session)

    session = await assessment_session_service.get_or_create_session(
        assessment.id, db_session
    )
    belief = {"a": 0.4, "b": 0.35, "c": 0.15, "d": 0.1}
    session = await assessment_session_service.save_session(
        session, db_session, belief=belief, status=SessionStatus.converged_cluster,
    )

    turn = await akinator_session_service.reject_leaves(
        assessment.id, ["a", "b"], AgeGroup.senior, db_session
    )

    assert "a" not in turn.session.belief
    assert "b" not in turn.session.belief
    assert set(turn.session.rejected_leaves) == {"a", "b"}


async def test_reject_leaves_exhausting_candidates_falls_back_to_inconclusive(
    db_session: AsyncSession,
):
    """Rejecting every remaining candidate at once must not surface the
    engine's raw ValueError — it's the one true dead end, handled by forcing
    an honest, no-confidence reveal instead of a 400."""
    await _ensure_seeded(db_session)
    assessment = await _make_assessment(db_session)

    session = await assessment_session_service.get_or_create_session(
        assessment.id, db_session
    )
    session = await assessment_session_service.save_session(
        session, db_session, belief={"a": 1.0}, status=SessionStatus.converged_single,
    )

    turn = await akinator_session_service.reject_leaves(
        assessment.id, ["a"], AgeGroup.senior, db_session
    )

    assert turn.decision.status == "reveal_cluster"
    assert turn.decision.reason == "ceiling"
    assert turn.decision.leaves == []
    assert turn.session.status == SessionStatus.exhausted_ceiling


async def test_go_back_reverts_to_the_same_question_and_prior_state(db_session: AsyncSession):
    """Going back undoes the last answer and re-serves that exact question —
    not a freshly-picked one — so the user can literally change that answer."""
    await _ensure_seeded(db_session)
    assessment = await _make_assessment(db_session)

    turn = await akinator_session_service.start_session(assessment.id, AgeGroup.senior, db_session)
    question = turn.next_question
    assert question is not None
    original_belief = dict(turn.session.belief)

    turn = await akinator_session_service.submit_answer(
        assessment.id, question.id, 0, AgeGroup.senior, db_session
    )
    assert turn.session.step == 1

    turn = await akinator_session_service.go_back(assessment.id, AgeGroup.senior, db_session)

    assert turn.next_question is not None
    assert turn.next_question.id == question.id
    assert turn.session.step == 0
    assert turn.session.asked_question_ids == []
    assert turn.session.belief == original_belief


async def test_go_back_repeatedly_restores_the_original_belief(db_session: AsyncSession):
    """Rewinding all the way to the start reconstructs the original uniform
    prior, not just an approximation of it."""
    await _ensure_seeded(db_session)
    assessment = await _make_assessment(db_session)

    turn = await akinator_session_service.start_session(assessment.id, AgeGroup.senior, db_session)
    original_belief = dict(turn.session.belief)

    answered = 0
    for _ in range(3):
        question = turn.next_question
        assert question is not None
        turn = await akinator_session_service.submit_answer(
            assessment.id, question.id, 0, AgeGroup.senior, db_session
        )
        answered += 1
        if turn.next_question is None:
            break  # converged early — nothing further to rewind past

    for _ in range(answered):
        turn = await akinator_session_service.go_back(assessment.id, AgeGroup.senior, db_session)

    assert turn.session.belief == original_belief
    assert turn.session.step == 0
    assert turn.session.asked_question_ids == []


async def test_go_back_past_a_rejection_still_excludes_the_rejected_leaf(db_session: AsyncSession):
    """Rewinding Q&A history must never resurrect a leaf the user explicitly
    rejected — reject_leaf/reject_leaves never write to the answer log, so
    their effect has to survive independently of how far back this rewinds."""
    await _ensure_seeded(db_session)
    assessment = await _make_assessment(db_session)

    question_result = await db_session.execute(
        select(AkinatorQuestion).where(AkinatorQuestion.is_active.is_(True)).limit(1)
    )
    question = question_result.scalar_one()

    leaves = await akinator_session_service._leaf_directions_for_age(db_session, AgeGroup.senior)
    initial_belief = {leaf.slug: 1 / len(leaves) for leaf in leaves}
    rejected_slug = leaves[0].slug

    session = await assessment_session_service.get_or_create_session(assessment.id, db_session)
    session = await assessment_session_service.save_session(
        session, db_session, belief=initial_belief, status=SessionStatus.in_progress,
    )
    assessment_session_service.log_answer(
        session, db_session, step=1, question_id=question.id,
        selected_option_index=0, belief_after=initial_belief,
    )
    session = await assessment_session_service.save_session(
        session, db_session,
        step=1, asked_question_ids=[str(question.id)], rejected_leaves=[rejected_slug],
    )

    turn = await akinator_session_service.go_back(assessment.id, AgeGroup.senior, db_session)

    assert turn.next_question is not None
    assert turn.next_question.id == question.id
    assert rejected_slug not in turn.session.belief


async def test_go_back_with_no_answers_raises(db_session: AsyncSession):
    await _ensure_seeded(db_session)
    assessment = await _make_assessment(db_session)
    await akinator_session_service.start_session(assessment.id, AgeGroup.senior, db_session)

    with pytest.raises(ValueError):
        await akinator_session_service.go_back(assessment.id, AgeGroup.senior, db_session)


async def test_go_back_after_a_reveal_raises(db_session: AsyncSession):
    """Out of scope for now: the reveal screen has its own way forward
    (reject/feedback), so going back is only available while a question is
    currently being shown."""
    await _ensure_seeded(db_session)
    assessment = await _make_assessment(db_session)

    session = await assessment_session_service.get_or_create_session(assessment.id, db_session)
    await assessment_session_service.save_session(
        session, db_session, belief={"a": 1.0}, status=SessionStatus.converged_single,
    )

    with pytest.raises(ValueError):
        await akinator_session_service.go_back(assessment.id, AgeGroup.senior, db_session)
