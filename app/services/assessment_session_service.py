import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.akinator_answer_log import AkinatorAnswerLog
from app.models.assessment_session import AssessmentSession, SessionStatus

# belief is a softmax output over leaf directions; floating-point drift across
# updates is expected, ~1% slack absorbs it without hiding a real bug.
BELIEF_SUM_TOLERANCE = 0.01


def validate_belief(belief: dict[str, float]) -> None:
    """Empty belief (no answer scored yet) is valid; otherwise Σ must be ~1.0."""
    if not belief:
        return
    total = sum(belief.values())
    if abs(total - 1.0) > BELIEF_SUM_TOLERANCE:
        raise ValueError(f"belief must sum to ~1.0, got {total}")


async def get_or_create_session(assessment_id: uuid.UUID, db: AsyncSession) -> AssessmentSession:
    result = await db.execute(
        select(AssessmentSession).where(AssessmentSession.assessment_id == assessment_id)
    )
    session = result.scalar_one_or_none()
    if session is not None:
        return session

    session = AssessmentSession(assessment_id=assessment_id)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def save_session(
    session: AssessmentSession,
    db: AsyncSession,
    *,
    belief: dict[str, float] | None = None,
    asked_question_ids: list[Any] | None = None,
    asked_axis_families: list[Any] | None = None,
    rejected_leaves: list[Any] | None = None,
    step: int | None = None,
    status: SessionStatus | None = None,
) -> AssessmentSession:
    if belief is not None:
        validate_belief(belief)
        session.belief = belief
    if asked_question_ids is not None:
        session.asked_question_ids = asked_question_ids
    if asked_axis_families is not None:
        session.asked_axis_families = asked_axis_families
    if rejected_leaves is not None:
        session.rejected_leaves = rejected_leaves
    if step is not None:
        session.step = step
    if status is not None:
        session.status = status

    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


def log_answer(
    session: AssessmentSession,
    db: AsyncSession,
    *,
    step: int,
    question_id: uuid.UUID,
    selected_option_index: int | None,
    belief_after: dict[str, float],
) -> None:
    """Queue one append-only history row for this answer. Not committed here —
    the caller's later save_session call commits it alongside the belief
    update it's part of (see akinator_session_service.submit_answer), so both
    land in one transaction."""
    db.add(AkinatorAnswerLog(
        session_id=session.id,
        step=step,
        question_id=question_id,
        selected_option_index=selected_option_index,
        belief_after=belief_after,
    ))


async def get_answer_log(session_id: uuid.UUID, db: AsyncSession) -> list[AkinatorAnswerLog]:
    """Full question -> option -> belief chain for a session, in answer order."""
    result = await db.execute(
        select(AkinatorAnswerLog)
        .where(AkinatorAnswerLog.session_id == session_id)
        .order_by(AkinatorAnswerLog.step)
    )
    return list(result.scalars().all())


async def save_feedback(
    session: AssessmentSession, db: AsyncSession, *, liked: bool, note: str | None
) -> AssessmentSession:
    session.liked = liked
    session.feedback_note = note
    session.feedback_at = datetime.now(timezone.utc)

    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session
