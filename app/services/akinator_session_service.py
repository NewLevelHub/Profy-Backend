"""Dialogue-session orchestration for the axis-driven Akinator engine.

Ties together persistence (assessment_session_service), pure math
(akinator_engine) and content (Direction leaves, AkinatorQuestion bank) into
one turn: next question, or reveal. `goal` (Assessment.goal) plays no role
here — the engine is the same regardless of goal; goal only shapes the
roadmap built later from the revealed direction(s).
"""
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.akinator_question import AkinatorQuestion
from app.models.assessment_session import AssessmentSession, SessionStatus
from app.models.direction import Direction
from app.models.profile import AgeGroup
from app.services import akinator_engine, assessment_session_service

# Guarantees check_stop falls past the age ceiling and returns a reveal
# instead of "continue" when the active question bank has run dry — reuses
# the already-tested ceiling fallback instead of duplicating cluster logic.
_FORCE_CEILING_STEP = 10**6


@dataclass(frozen=True, slots=True)
class SessionTurn:
    """What start_session / submit_answer hand back to the caller."""
    session: AssessmentSession
    decision: akinator_engine.StopDecision
    next_question: AkinatorQuestion | None


def _fits_age(direction: Direction, age_group: AgeGroup) -> bool:
    groups = direction.age_groups or []
    return not groups or age_group.value in groups


async def _leaf_directions_for_age(db: AsyncSession, age_group: AgeGroup) -> list[Direction]:
    result = await db.execute(select(Direction).where(Direction.is_leaf.is_(True)))
    return [d for d in result.scalars().all() if _fits_age(d, age_group)]


async def _leaf_profiles_for(db: AsyncSession, belief: dict[str, float]) -> dict[str, dict[str, int]]:
    result = await db.execute(select(Direction).where(Direction.slug.in_(belief.keys())))
    return {d.slug: (d.profile or {}) for d in result.scalars().all()}


async def _active_questions(db: AsyncSession) -> list[AkinatorQuestion]:
    result = await db.execute(select(AkinatorQuestion).where(AkinatorQuestion.is_active.is_(True)))
    return list(result.scalars().all())


def _status_for(decision: akinator_engine.StopDecision) -> SessionStatus:
    if decision.status == "reveal_single":
        return SessionStatus.converged_single
    if decision.reason == "ceiling":
        return SessionStatus.exhausted_ceiling
    return SessionStatus.converged_cluster


async def _advance(
    session: AssessmentSession,
    db: AsyncSession,
    age_group: AgeGroup,
    *,
    belief: dict[str, float] | None = None,
    step: int | None = None,
    asked_question_ids: list | None = None,
    asked_axis_families: list | None = None,
) -> SessionTurn:
    """Persist any given state change, then decide continue-vs-reveal and
    either pick the next question or persist the reveal status. Shared by
    start_session (after the initial belief is set) and submit_answer (after
    an answer is scored)."""
    if any(v is not None for v in (belief, step, asked_question_ids, asked_axis_families)):
        session = await assessment_session_service.save_session(
            session, db,
            belief=belief, step=step,
            asked_question_ids=asked_question_ids, asked_axis_families=asked_axis_families,
        )

    decision = akinator_engine.check_stop(session.belief, session.step, age_group.value)

    if decision.status == "continue":
        leaf_profiles = await _leaf_profiles_for(db, session.belief)
        candidates = await _active_questions(db)
        next_question = akinator_engine.select_next_question(
            session, candidates, leaf_profiles, age_group.value
        )
        if next_question is not None:
            return SessionTurn(session=session, decision=decision, next_question=next_question)
        # Content exhausted before either stopping rule fired — force a
        # cluster reveal rather than stalling forever (a valid outcome).
        decision = akinator_engine.check_stop(session.belief, _FORCE_CEILING_STEP, age_group.value)

    if session.status == SessionStatus.in_progress:
        session = await assessment_session_service.save_session(
            session, db, status=_status_for(decision)
        )
    return SessionTurn(session=session, decision=decision, next_question=None)


async def start_session(
    assessment_id: uuid.UUID, age_group: AgeGroup, db: AsyncSession
) -> SessionTurn:
    """Create (or resume) the session, seed a uniform belief over this age
    group's leaf directions on first call, and return the first question (or
    an immediate reveal, for a degenerate single-leaf catalog)."""
    session = await assessment_session_service.get_or_create_session(assessment_id, db)

    if session.belief:
        return await _advance(session, db, age_group)

    leaves = await _leaf_directions_for_age(db, age_group)
    if not leaves:
        raise ValueError(f"no leaf directions available for age_group={age_group.value!r}")

    belief = {leaf.slug: 1 / len(leaves) for leaf in leaves}
    return await _advance(session, db, age_group, belief=belief)


async def submit_answer(
    assessment_id: uuid.UUID,
    question_id: uuid.UUID,
    option_index: int | None,
    age_group: AgeGroup,
    db: AsyncSession,
) -> SessionTurn:
    """Score one answer and advance the session. `option_index=None` is
    "не знаю" — a real, recorded answer with zero axis contribution (identity
    update), not a skip. Guard clauses (explicit errors, no silent fallback):
    session not started, question not found, question not valid for this
    session's age, question already answered, option_index out of range."""
    result = await db.execute(
        select(AssessmentSession).where(AssessmentSession.assessment_id == assessment_id)
    )
    session = result.scalar_one_or_none()
    if session is None or not session.belief:
        raise ValueError(f"no akinator session in progress for assessment {assessment_id}")

    question = await db.get(AkinatorQuestion, question_id)
    if question is None:
        raise ValueError(f"question {question_id} not found")

    if not akinator_engine.age_variant_matches(question, age_group.value):
        raise ValueError(f"question {question_id} does not belong to this session")

    already_asked = {str(qid) for qid in (session.asked_question_ids or [])}
    if str(question_id) in already_asked:
        raise ValueError(f"question {question_id} was already answered in this session")

    if option_index is not None and not (0 <= option_index < len(question.options)):
        raise ValueError(f"option_index {option_index} out of range for question {question_id}")

    answer_weights = (
        question.options[option_index].get("axis_weights", {}) if option_index is not None else {}
    )
    leaf_profiles = await _leaf_profiles_for(db, session.belief)
    new_belief = akinator_engine.update_belief(session.belief, answer_weights, leaf_profiles)

    touched_families = {family.value for family in akinator_engine.question_axis_families(question)}
    new_asked_families = sorted({*session.asked_axis_families, *touched_families})
    new_asked_ids = [*session.asked_question_ids, str(question_id)]
    new_step = session.step + 1

    assessment_session_service.log_answer(
        session, db,
        step=new_step,
        question_id=question_id,
        selected_option_index=option_index,
        belief_after=new_belief,
    )

    return await _advance(
        session, db, age_group,
        belief=new_belief,
        step=new_step,
        asked_question_ids=new_asked_ids,
        asked_axis_families=new_asked_families,
    )


async def submit_feedback(
    assessment_id: uuid.UUID, liked: bool, note: str | None, db: AsyncSession
) -> AssessmentSession:
    """Record liked/note for a session — only once it has reached a reveal,
    since feedback judges a *result*, and a session still picking questions
    has no result yet to judge."""
    result = await db.execute(
        select(AssessmentSession).where(AssessmentSession.assessment_id == assessment_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise ValueError(f"no akinator session found for assessment {assessment_id}")
    if session.status == SessionStatus.in_progress:
        raise ValueError("feedback can only be submitted after a reveal")

    return await assessment_session_service.save_feedback(session, db, liked=liked, note=note)


async def reject_leaf(
    assessment_id: uuid.UUID, leaf_slug: str, age_group: AgeGroup, db: AsyncSession
) -> SessionTurn:
    """Handle an explicit "this doesn't fit" from the user — distinct from
    the engine's own uncertainty (StopDecision.status == "reveal_cluster" in
    check_stop). Strongly demotes leaf_slug (removed from belief entirely,
    not just discounted — see akinator_engine.reject_leaf) and re-derives the
    turn, so the same leaf can never resurface in this session. Only valid
    once a reveal has actually happened — nothing to reject before then."""
    result = await db.execute(
        select(AssessmentSession).where(AssessmentSession.assessment_id == assessment_id)
    )
    session = result.scalar_one_or_none()
    if session is None or not session.belief:
        raise ValueError(f"no akinator session in progress for assessment {assessment_id}")
    if session.status == SessionStatus.in_progress:
        raise ValueError("a leaf can only be rejected after a reveal")

    new_belief = akinator_engine.reject_leaf(session.belief, leaf_slug)
    new_rejected = [*session.rejected_leaves, leaf_slug]

    # Reopen the session so _advance's finalize-once guard re-fires for the
    # new decision, instead of treating it as already converged.
    session = await assessment_session_service.save_session(
        session, db,
        belief=new_belief,
        rejected_leaves=new_rejected,
        status=SessionStatus.in_progress,
    )
    return await _advance(session, db, age_group)
