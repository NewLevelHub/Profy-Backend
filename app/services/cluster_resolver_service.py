import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.akinator_question import AkinatorQuestion
from app.models.assessment_session import AssessmentSession, SessionStatus
from app.models.profile import AgeGroup
from app.services import akinator_engine, assessment_session_service
from app.services.akinator_session_service import SessionTurn, _leaf_profiles_for

logger = logging.getLogger(__name__)


async def get_eligible_questions(
    session: AssessmentSession,
    db: AsyncSession,
    age_group: str,
) -> list[AkinatorQuestion]:
    """Retrieve active resolving questions (resolves_pair) that are applicable

    for the leaves in the current session's top cluster.
    """
    decision = akinator_engine.check_stop(session.belief, session.step, age_group)
    cluster_leaves = set(decision.leaves)

    result = await db.execute(
        select(AkinatorQuestion).where(AkinatorQuestion.is_active.is_(True))
    )
    all_qs = result.scalars().all()
    by_id = {str(q.id): q for q in all_qs}

    asked_ids = {str(qid) for qid in (session.asked_question_ids or [])}

    # Which cluster leaves has ANY already-asked question (main phase or an
    # earlier resolve_step round) already put in front of the user via a
    # named resolves_pair — used below to prefer resolvers bringing FRESH
    # cluster coverage over ones that only re-cover leaves that already got
    # their own dedicated question.
    already_addressed: set[str] = set()
    for qid in asked_ids:
        asked_q = by_id.get(qid)
        if asked_q and asked_q.resolves_pair:
            already_addressed |= set(asked_q.resolves_pair) & cluster_leaves

    eligible = []
    for q in all_qs:
        if str(q.id) in asked_ids:
            continue
        if not akinator_engine.age_variant_matches(q, age_group):
            continue
        # Both (or at least 2) leaves in the resolves_pair must be in the current cluster
        if q.resolves_pair and len(set(q.resolves_pair) & cluster_leaves) >= 2:
            eligible.append(q)

    # Sort by (1) how much FRESH cluster coverage this question brings —
    # cluster leaves no earlier question already addressed — descending,
    # (2) total cluster overlap descending, (3) curation order ascending as
    # a final tiebreak. Plain curation-order sorting (pre-2026-07-29) could
    # spend one of only 3 precious resolve_step questions on a resolver
    # that names 2 of 3 cluster leaves while leaving the third — potentially
    # the one genuinely in doubt — completely unaddressed, even when a
    # different eligible question would have covered it instead. This
    # makes the scarce resolve-phase budget try to touch every cluster
    # member at least once before repeating.
    def _sort_key(q: AkinatorQuestion) -> tuple[int, int, int]:
        overlap = set(q.resolves_pair or []) & cluster_leaves
        fresh = len(overlap - already_addressed)
        return (-fresh, -len(overlap), q.order)

    eligible.sort(key=_sort_key)
    return eligible


async def resolve_cluster_turn(
    assessment_id: uuid.UUID,
    question_id: uuid.UUID | None,
    selected_option_index: int | None,
    age_group: AgeGroup,
    db: AsyncSession,
) -> SessionTurn:
    """Orchestrate one turn of the cluster resolver flow.

    Can be called with question_id=None to start/resume, or with question_id to submit an answer.
    """
    result = await db.execute(
        select(AssessmentSession).where(AssessmentSession.assessment_id == assessment_id)
    )
    session = result.scalar_one_or_none()
    if session is None or not session.belief:
        raise ValueError(f"no akinator session in progress for assessment {assessment_id}")

    if session.status != SessionStatus.converged_cluster:
        raise ValueError("Разрешение противоречий возможно только для результатов-кластеров")

    # Start/Resume phase
    if question_id is None:
        eligible = await get_eligible_questions(session, db, age_group.value)
        if not eligible or session.resolve_step >= 3:
            decision = akinator_engine.check_stop(session.belief, session.step, age_group.value)
            return SessionTurn(session=session, decision=decision, next_question=None)

        decision = akinator_engine.check_stop(session.belief, session.step, age_group.value)
        return SessionTurn(session=session, decision=decision, next_question=eligible[0])

    # Answer submission phase
    question = await db.get(AkinatorQuestion, question_id)
    if question is None:
        raise ValueError(f"question {question_id} not found")

    eligible = await get_eligible_questions(session, db, age_group.value)
    if question_id not in {q.id for q in eligible}:
        raise ValueError(f"question {question_id} is not eligible for cluster resolution")

    if selected_option_index is not None and not (0 <= selected_option_index < len(question.options)):
        raise ValueError(f"selected_option_index {selected_option_index} out of range")

    # Scored belief update
    answer_weights = (
        question.options[selected_option_index].get("axis_weights", {})
        if selected_option_index is not None
        else {}
    )
    leaf_profiles = await _leaf_profiles_for(db, session.belief)
    new_belief = akinator_engine.update_belief(session.belief, answer_weights, leaf_profiles)

    new_step = session.step + 1
    new_resolve_step = session.resolve_step + 1

    # Log answer
    assessment_session_service.log_answer(
        session,
        db,
        step=new_step,
        question_id=question_id,
        selected_option_index=selected_option_index,
        belief_after=new_belief,
    )

    touched_families = {
        family.value for family in akinator_engine.question_axis_families(question)
    }
    new_asked_families = sorted({*session.asked_axis_families, *touched_families})
    new_asked_ids = [*session.asked_question_ids, str(question_id)]

    # Check Stop decision for the updated belief
    decision = akinator_engine.check_stop(new_belief, new_step, age_group.value)

    if decision.status == "reveal_single":
        # Successfully resolved to a single winner
        session = await assessment_session_service.save_session(
            session,
            db,
            belief=new_belief,
            step=new_step,
            asked_question_ids=new_asked_ids,
            asked_axis_families=new_asked_families,
            resolve_step=new_resolve_step,
            status=SessionStatus.converged_single,
        )
        logger.info(
            "Cluster resolved successfully: assessment_id=%s, winner=%s, resolve_step=%s",
            assessment_id,
            decision.leaves[0],
            new_resolve_step,
        )
        return SessionTurn(session=session, decision=decision, next_question=None)

    if new_resolve_step >= 3:
        # Budget exhausted, cluster remains a cluster
        session = await assessment_session_service.save_session(
            session,
            db,
            belief=new_belief,
            step=new_step,
            asked_question_ids=new_asked_ids,
            asked_axis_families=new_asked_families,
            resolve_step=new_resolve_step,
            status=SessionStatus.converged_cluster,
        )
        forced_decision = akinator_engine.StopDecision(
            status="reveal_cluster",
            leaves=decision.leaves if decision.status == "reveal_cluster" else list(decision.leaves),
            reason="ceiling",
        )
        logger.info(
            "Cluster resolver budget exhausted: assessment_id=%s, resolve_step=%s. Cluster remains.",
            assessment_id,
            new_resolve_step,
        )
        return SessionTurn(session=session, decision=forced_decision, next_question=None)

    # Continue check
    next_eligible = await get_eligible_questions(
        AssessmentSession(
            belief=new_belief,
            step=new_step,
            asked_question_ids=new_asked_ids,
            asked_axis_families=new_asked_families,
        ),
        db,
        age_group.value,
    )
    if not next_eligible:
        # No more questions, cluster remains a cluster
        session = await assessment_session_service.save_session(
            session,
            db,
            belief=new_belief,
            step=new_step,
            asked_question_ids=new_asked_ids,
            asked_axis_families=new_asked_families,
            resolve_step=new_resolve_step,
            status=SessionStatus.converged_cluster,
        )
        forced_decision = akinator_engine.StopDecision(
            status="reveal_cluster",
            leaves=decision.leaves if decision.status == "reveal_cluster" else list(decision.leaves),
            reason="ceiling",
        )
        logger.info(
            "Cluster resolver ran out of questions: assessment_id=%s, resolve_step=%s. Cluster remains.",
            assessment_id,
            new_resolve_step,
        )
        return SessionTurn(session=session, decision=forced_decision, next_question=None)

    # Continue resolving
    session = await assessment_session_service.save_session(
        session,
        db,
        belief=new_belief,
        step=new_step,
        asked_question_ids=new_asked_ids,
        asked_axis_families=new_asked_families,
        resolve_step=new_resolve_step,
    )
    return SessionTurn(session=session, decision=decision, next_question=next_eligible[0])
