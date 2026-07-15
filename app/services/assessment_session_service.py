import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    if step is not None:
        session.step = step
    if status is not None:
        session.status = status

    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session
