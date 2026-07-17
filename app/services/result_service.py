"""Final akinator result — the completed-assessment counterpart to the
in-test reveal (see akinator_report_service). No LLM call and no new
computation: everything here is assembled from data the akinator engine
already produced (Assessment.selected_direction_slug, AssessmentSession.belief,
Direction.profile), so this can never 503.
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.axes import AXIS_CATALOG
from app.models.assessment import Assessment, AssessmentStatus
from app.models.assessment_session import AssessmentSession, SessionStatus
from app.models.direction import Direction
from app.schemas.akinator_session import RevealLeaf
from app.schemas.result import AkinatorResultResponse, ResultAxisHighlight
from app.services.akinator_report_service import BACKUP_COUNT, REPORT_MESSAGES

_TOP_AXES_COUNT = 6

_AXIS_LABELS: dict[str, str] = {axis.code: axis.label_ru for axis in AXIS_CATALOG}

# Mirrors akinator_report_service.build_reveal_report's kind selection, keyed
# off the persisted session status instead of a live StopDecision.
_MESSAGE_KEY_BY_STATUS: dict[SessionStatus, str] = {
    SessionStatus.converged_single: "confident",
    SessionStatus.converged_cluster: "uncertain",
    SessionStatus.exhausted_ceiling: "uncertain",
}


def matched_axes_for(profile: dict[str, int]) -> list[ResultAxisHighlight]:
    """The direction's own standout axes, strongest first. Pure function, no
    DB — there's no retained per-axis signal for the student to compare
    against (belief only tracks likelihood per leaf, not per axis), so this
    describes what defines the profession rather than "how well you scored"."""
    ranked = sorted(
        (item for item in profile.items() if item[1] != 0),
        key=lambda item: (-abs(item[1]), item[0]),
    )
    return [
        ResultAxisHighlight(code=code, label_ru=_AXIS_LABELS.get(code, code), direction_value=value)
        for code, value in ranked[:_TOP_AXES_COUNT]
    ]


def _message_for(session: AssessmentSession) -> str:
    key = _MESSAGE_KEY_BY_STATUS.get(session.status, "uncertain")
    if session.rejected_leaves:
        key += "_after_rejection"
    return REPORT_MESSAGES[key]


async def _backups_for(session: AssessmentSession, exclude_slug: str, db: AsyncSession) -> list[RevealLeaf]:
    ranked = sorted(session.belief.items(), key=lambda item: item[1], reverse=True)
    slugs = [slug for slug, _ in ranked if slug != exclude_slug][:BACKUP_COUNT]
    if not slugs:
        return []

    result = await db.execute(select(Direction).where(Direction.slug.in_(slugs)))
    directions_by_slug = {d.slug: d for d in result.scalars().all()}

    section_ids = {d.parent_id for d in directions_by_slug.values() if d.parent_id is not None}
    sections_result = await db.execute(select(Direction).where(Direction.id.in_(section_ids)))
    section_name_by_id = {s.id: s.name for s in sections_result.scalars().all()}

    return [
        RevealLeaf(
            slug=slug,
            name=direction.name,
            direction=section_name_by_id.get(direction.parent_id, ""),
            description=direction.description,
        )
        for slug in slugs
        if (direction := directions_by_slug.get(slug)) is not None
    ]


async def get_result(assessment_id: uuid.UUID, db: AsyncSession) -> AkinatorResultResponse:
    assessment = await db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    if assessment.status != AssessmentStatus.completed or assessment.selected_direction_slug is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not ready yet")

    direction = (
        await db.execute(
            select(Direction).where(
                Direction.slug == assessment.selected_direction_slug,
                Direction.is_leaf.is_(True),
            )
        )
    ).scalar_one_or_none()
    if direction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Direction not found")

    session = (
        await db.execute(
            select(AssessmentSession).where(AssessmentSession.assessment_id == assessment_id)
        )
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not ready yet")

    backups = await _backups_for(session, assessment.selected_direction_slug, db)

    return AkinatorResultResponse(
        assessment_id=assessment.id,
        direction_slug=direction.slug,
        direction_name=direction.name,
        direction_description=direction.description,
        message=_message_for(session),
        matched_axes=matched_axes_for(direction.profile or {}),
        backups=backups,
        created_at=assessment.created_at,
    )
