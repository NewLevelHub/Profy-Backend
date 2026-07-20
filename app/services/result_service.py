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
from sqlalchemy.orm import selectinload

from app.core.axes import AXIS_CATALOG
from app.models.akinator_answer_log import AkinatorAnswerLog
from app.models.akinator_question import AkinatorQuestion
from app.models.assessment import Assessment, AssessmentStatus
from app.models.assessment_session import AssessmentSession
from app.models.direction import Direction
from app.models.program import Program
from app.models.university import University
from app.schemas.akinator_session import RevealLeaf
from app.schemas.result import AkinatorResultResponse, ChildAxisSignal, ResultAxisHighlight
from app.services.akinator_report_service import BACKUP_COUNT, REPORT_MESSAGES
from app.services.program_direction_resolver import program_direction_slugs_for

_TOP_AXES_COUNT = 6
_RECOMMENDED_PROGRAMS_LIMIT = 5
# How many of the child's own strongest/weakest axes to surface — separate
# from _TOP_AXES_COUNT, which caps the profession's own axis profile.
_STRENGTHS_COUNT = 3
_GROWTH_COUNT = 3

_AXIS_LABELS: dict[str, str] = {axis.code: axis.label_ru for axis in AXIS_CATALOG}


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


def _child_strengths_and_growth(
    totals: dict[str, float],
) -> tuple[list[ChildAxisSignal], list[ChildAxisSignal]]:
    """Split the child's own summed axis scores (see _child_axis_totals) into
    strengths (positive, strongest first) and growth areas (negative,
    weakest first) — pure function, same shape as matched_axes_for but over
    a different signal: what the child actually answered, not what the
    profession itself needs."""
    strengths = sorted(
        (item for item in totals.items() if item[1] > 0),
        key=lambda item: item[1],
        reverse=True,
    )[:_STRENGTHS_COUNT]
    growth = sorted(
        (item for item in totals.items() if item[1] < 0),
        key=lambda item: item[1],
    )[:_GROWTH_COUNT]

    return (
        [ChildAxisSignal(code=code, label_ru=_AXIS_LABELS.get(code, code), score=score) for code, score in strengths],
        [ChildAxisSignal(code=code, label_ru=_AXIS_LABELS.get(code, code), score=score) for code, score in growth],
    )


async def _child_axis_totals(session_id: uuid.UUID, db: AsyncSession) -> dict[str, float]:
    """Sum the axis_weights of every option the child actually selected
    across the whole session, straight from the answer log — the most
    direct signal of what the child answered, independent of which
    profession the answers happened to lead to."""
    result = await db.execute(
        select(AkinatorAnswerLog).where(
            AkinatorAnswerLog.session_id == session_id,
            AkinatorAnswerLog.selected_option_index.is_not(None),
        )
    )
    logs = result.scalars().all()
    if not logs:
        return {}

    question_ids = {log.question_id for log in logs}
    questions_result = await db.execute(
        select(AkinatorQuestion).where(AkinatorQuestion.id.in_(question_ids))
    )
    questions_by_id = {q.id: q for q in questions_result.scalars().all()}

    totals: dict[str, float] = {}
    for log in logs:
        question = questions_by_id.get(log.question_id)
        if question is None:
            continue
        weights = question.options[log.selected_option_index].get("axis_weights", {})
        for axis_code, weight in weights.items():
            totals[axis_code] = totals.get(axis_code, 0) + weight
    return totals


def _message_for(session: AssessmentSession) -> str:
    """The Results page always shows a direction the user explicitly
    confirmed (assessment.selected_direction_slug is only ever set by a
    "liked" feedback — see akinator_session_service.submit_feedback), no
    matter whether the akinator engine itself converged on a single winner,
    landed on a cluster, or hit the question ceiling. So the message here is
    always the "confident" framing — the engine's own convergence status
    (session.status) reflects uncertainty from *before* the child chose,
    which no longer applies once they've picked and confirmed one."""
    key = "confident_after_rejection" if session.rejected_leaves else "confident"
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
            professions=direction.professions or [],
        )
        for slug in slugs
        if (direction := directions_by_slug.get(slug)) is not None
    ]


async def _recommended_programs_for(selected_slug: str, db: AsyncSession) -> list[Program]:
    """Return Astana programs matching the test result profession or its section."""
    direction_slugs = await program_direction_slugs_for(selected_slug, db)
    result = await db.execute(
        select(Program)
        .options(selectinload(Program.university))
        .join(Program.university)
        .where(
            Program.direction_slug.in_(direction_slugs),
            University.country == "Казахстан",
            University.city == "Астана",
        )
        .limit(_RECOMMENDED_PROGRAMS_LIMIT)
    )
    return list(result.scalars().all())


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
    recommended_programs = await _recommended_programs_for(assessment.selected_direction_slug, db)
    child_totals = await _child_axis_totals(session.id, db)
    strengths, growth_areas = _child_strengths_and_growth(child_totals)

    return AkinatorResultResponse(
        assessment_id=assessment.id,
        direction_slug=direction.slug,
        direction_name=direction.name,
        direction_description=direction.description,
        professions=direction.professions or [],
        message=_message_for(session),
        matched_axes=matched_axes_for(direction.profile or {}),
        strengths=strengths,
        growth_areas=growth_areas,
        backups=backups,
        recommended_programs=recommended_programs,
        created_at=assessment.created_at,
    )
