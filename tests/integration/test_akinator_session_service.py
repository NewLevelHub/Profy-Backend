import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.assessment import Assessment, AssessmentGoal
from app.models.assessment_session import SessionStatus
from app.models.direction import Direction
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import akinator_session_service
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
