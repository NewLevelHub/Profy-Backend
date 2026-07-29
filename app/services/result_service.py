"""Final akinator result — the completed-assessment counterpart to the
in-test reveal (see akinator_report_service). No LLM call and no new
computation: everything here is assembled from data the akinator engine
already produced (Assessment.selected_direction_slug, AssessmentSession.belief,
Direction.profile), so this can never 503.
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import Text, cast, select
from sqlalchemy.dialects.postgresql import ARRAY, array as pg_array
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.axes import AXIS_CATALOG, AXIS_GROWTH_COPY, AXIS_STRENGTH_COPY
from app.models.akinator_answer_log import AkinatorAnswerLog
from app.models.akinator_question import AkinatorQuestion
from app.models.assessment import Assessment, AssessmentStatus
from app.models.assessment_session import AssessmentSession
from app.models.direction import Direction
from app.models.known_profession_quiz_log import KnownProfessionQuizLog
from app.models.profile import Profile
from app.models.program import Program
from app.models.university import University
from app.schemas.akinator_session import RevealLeaf
from app.schemas.result import AkinatorResultResponse, AxisComparisonItem, AxisGrowthExplanation
from app.services.akinator_report_service import BACKUP_COUNT, REPORT_MESSAGES
from app.services.program_direction_resolver import program_direction_slugs_for

_RECOMMENDED_PROGRAMS_LIMIT = 5
# How many axes to surface per side of the comparison.
_MATCH_COUNT = 4
_GROWTH_COUNT = 4
# child_score >= this counts as "meets the direction's need" (match), below
# it counts as "growth". 0 is the simplest reasonable cut given child_score
# is a signed average of axis_weights — revisit once real session data shows
# whether a median-based cut per session tells a better story.
_MATCH_THRESHOLD = 0.0

_AXIS_LABELS: dict[str, str] = {axis.code: axis.label_ru for axis in AXIS_CATALOG}


def _split_by_threshold(candidates: dict[str, float]) -> tuple[list[str], list[str]]:
    """Split axis codes by _MATCH_THRESHOLD: >= it is a match (strongest
    first), below it is growth (weakest/largest-gap first). Pure ranking —
    doesn't know or care whether `candidates` came from the direction's own
    needs or the whole-session fallback (see _axis_comparison_for)."""
    match_codes = sorted(
        (code for code, score in candidates.items() if score >= _MATCH_THRESHOLD),
        key=lambda code: candidates[code],
        reverse=True,
    )[:_MATCH_COUNT]
    growth_codes = sorted(
        (code for code, score in candidates.items() if score < _MATCH_THRESHOLD),
        key=lambda code: candidates[code],
    )[:_GROWTH_COUNT]
    return match_codes, growth_codes


def _axis_comparison_for(
    profile: dict[str, int], child_scores: dict[str, float]
) -> tuple[list[AxisComparisonItem], list[AxisComparisonItem], bool]:
    """Compare the direction's own needs against the child's normalized
    per-axis signal (see child_axis_scores). Only axes the direction
    actually leans into (profile > 0) are considered, and only where the
    child's answers actually touched that axis — no axis is ever assigned a
    fake neutral score just to have something to show.

    If that overlap is empty (the session's questions never happened to
    touch any axis this direction needs — rare, but real: which axes get
    asked depends on the adaptive question path, not on the final
    direction), there is nothing honest to say about *this* direction
    specifically. Rather than showing nothing, fall back to the child's
    strongest/weakest axes across the whole session, unfiltered by this
    direction's profile — still entirely real signal, just not scoped to
    this profession. The caller must label this case differently (see
    AkinatorResultResponse.is_direction_specific); the returned bool here
    says which mode was used."""
    relevant = {
        code: child_scores[code] for code, value in profile.items() if value > 0 and code in child_scores
    }

    is_direction_specific = bool(relevant)
    candidates = relevant if is_direction_specific else child_scores
    profile_values = profile if is_direction_specific else {}

    match_codes, growth_codes = _split_by_threshold(candidates)

    match_items = [
        AxisComparisonItem(
            code=code,
            label_ru=_AXIS_LABELS.get(code, code),
            profile_value=profile_values.get(code),
            child_score=round(candidates[code], 2),
            strength_phrase=AXIS_STRENGTH_COPY.get(code),
        )
        for code in match_codes
    ]
    growth_items = [
        AxisComparisonItem(
            code=code,
            label_ru=_AXIS_LABELS.get(code, code),
            profile_value=profile_values.get(code),
            child_score=round(candidates[code], 2),
            explanation=_growth_explanation_for(code),
        )
        for code in growth_codes
    ]
    return match_items, growth_items, is_direction_specific


def _growth_explanation_for(code: str) -> AxisGrowthExplanation | None:
    copy = AXIS_GROWTH_COPY.get(code)
    if copy is None:
        return None
    return AxisGrowthExplanation(meaning=copy.meaning, suggestion=copy.suggestion)


async def child_axis_scores(session_id: uuid.UUID, db: AsyncSession) -> dict[str, float]:
    """Average axis_weight per axis across every option the child actually
    selected in the session, straight from the answer log. Averaging (rather
    than summing, as this used to) keeps axes touched by many questions from
    automatically outranking axes touched by few — otherwise the comparison
    in _axis_comparison_for would be measuring "how often this axis came up"
    more than "how the child actually leaned on it".

    Public (no leading underscore): reused by student_context.py to ground
    the direction-roadmap prompt in the same real per-axis signal shown on
    the /results page, instead of only the direction's own ideal profile."""
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

    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for log in logs:
        question = questions_by_id.get(log.question_id)
        if question is None:
            continue
        weights = question.options[log.selected_option_index].get("axis_weights", {})
        for axis_code, weight in weights.items():
            sums[axis_code] = sums.get(axis_code, 0) + weight
            counts[axis_code] = counts.get(axis_code, 0) + 1
    return {code: sums[code] / counts[code] for code in sums}


def _message_for(session: AssessmentSession | None) -> str:
    """The Results page always shows a direction the user explicitly
    confirmed (assessment.selected_direction_slug is only ever set by a
    "liked" feedback — see akinator_session_service.submit_feedback), no
    matter whether the akinator engine itself converged on a single winner,
    landed on a cluster, or hit the question ceiling. So the message here is
    always the "confident" framing — the engine's own convergence status
    (session.status) reflects uncertainty from *before* the child chose,
    which no longer applies once they've picked and confirmed one.

    `session` is None for sessionless assessments (known-profession flow —
    see known_profession_service), which never ran the belief-walk engine
    and so never rejected any leaves either — falls back to "confident"."""
    key = "confident_after_rejection" if session and session.rejected_leaves else "confident"
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


async def _completion_stats_for(
    assessment: Assessment, session: AssessmentSession | None, db: AsyncSession
) -> tuple[int | None, int | None]:
    """Real progress/confidence numbers for the completed-test summary shown
    on the home screen — never invented, just surfaced from whichever flow
    produced this assessment.

    Akinator flow: session.step is how many questions were actually
    answered; session.belief is the engine's own per-direction probability,
    so the selected direction's share of it is the same "match" number
    admin's session view already shows as top_directions[].probability.
    Known-profession flow never runs this engine, so its own quiz log
    (percent + answers) is used instead. Both are None only when neither
    signal exists (e.g. an assessment that predates this tracking)."""
    if session is not None:
        match_percent = None
        belief_score = session.belief.get(assessment.selected_direction_slug)
        if belief_score is not None:
            match_percent = round(belief_score * 100)
        return session.step, match_percent

    quiz_log = (
        await db.execute(
            select(KnownProfessionQuizLog)
            .where(KnownProfessionQuizLog.assessment_id == assessment.id)
            .order_by(KnownProfessionQuizLog.created_at.desc())
        )
    ).scalars().first()
    if quiz_log is None:
        return None, None
    return len(quiz_log.answers), quiz_log.percent


async def recommended_programs_for(
    selected_slug: str,
    db: AsyncSession,
    city: str | None = None,
) -> list[Program]:
    """Return programs matching the test result profession or its section.

    If *city* is provided, results are filtered to that city only.
    When *city* is None no city filter is applied (all cities are included).
    The country filter (Kazakhstan) always remains active.

    Public (no leading underscore): also reused by roadmap_builder.py for the
    direction roadmap's university_requirements — same real Program rows, no
    LLM involved, same precedent as child_axis_scores above."""
    direction_slugs = await program_direction_slugs_for(selected_slug, db)
    conditions = [
        # ?| operator: JSONB column has any element from the given text array.
        Program.direction_slugs.op("?|")(
            cast(pg_array(direction_slugs), ARRAY(Text))
        ),
        University.country == "Казахстан",
    ]
    if city is not None:
        conditions.append(University.city == city)
    result = await db.execute(
        select(Program)
        .options(selectinload(Program.university))
        .join(Program.university)
        .where(*conditions)
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

    # None for sessionless assessments (known-profession flow — see
    # known_profession_service), which never ran the belief-walk engine.
    # Every downstream use below already degrades to an empty/neutral result
    # for that case instead of erroring — mirrors student_context.py's
    # `belief = session.belief if session else {}` handling for the same
    # sessionless case in the roadmap-prompt path.
    session = (
        await db.execute(
            select(AssessmentSession).where(AssessmentSession.assessment_id == assessment_id)
        )
    ).scalar_one_or_none()

    profile = await db.get(Profile, assessment.profile_id)
    user_city: str | None = profile.city if profile is not None else None

    backups = await _backups_for(session, assessment.selected_direction_slug, db) if session else []
    recommended_programs = await recommended_programs_for(
        assessment.selected_direction_slug, db, city=user_city
    )
    child_scores = await child_axis_scores(session.id, db) if session else {}
    matches, growth_areas, is_direction_specific = _axis_comparison_for(
        direction.profile or {}, child_scores
    )
    questions_answered, match_percent = await _completion_stats_for(assessment, session, db)

    return AkinatorResultResponse(
        assessment_id=assessment.id,
        direction_slug=direction.slug,
        direction_name=direction.name,
        direction_description=direction.description,
        professions=direction.professions or [],
        message=_message_for(session),
        matches=matches,
        growth_areas=growth_areas,
        is_direction_specific=is_direction_specific,
        backups=backups,
        recommended_programs=recommended_programs,
        created_at=assessment.created_at,
        completed_at=assessment.completed_at,
        questions_answered=questions_answered,
        match_percent=match_percent,
    )
