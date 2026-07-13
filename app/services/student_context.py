"""Assemble a complete StudentContext from stored data.

Single source of truth for "everything we know about this student" — profile,
chosen goal, the stored analysis (report), age-appropriate matched directions,
and the raw signals that scoring drops (values, goal-clarification, university
preferences). Consumed by the roadmap builder (and, in Phase 3, the LLM).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult
from app.models.artifact import Artifact
from app.models.assessment import Assessment
from app.models.direction_inquiry import DirectionInquiry
from app.models.profile import Profile
from app.schemas.student_context import (
    ContextArtifact,
    ContextDirection,
    ContextInquiry,
    StudentContext,
)
from app.services import ai_service, assessment_service, scoring_service

# Likert index (0-4) at or below which an answer reads as "not me" — and at or
# above which it reads as "that's me".
_LOW_ANSWER = 1
_HIGH_ANSWER = 3


def _context_inquiry(inquiry: DirectionInquiry | None) -> ContextInquiry | None:
    """Split the inquiry answers into what the student owned and what they didn't."""
    if inquiry is None:
        return None
    low: list[str] = []
    high: list[str] = []
    questions = inquiry.questions or []
    answers = inquiry.answers or []
    for question, answer in zip(questions, answers):
        text = question.get("text") if isinstance(question, dict) else None
        if not text or not isinstance(answer, int):
            continue
        if answer <= _LOW_ANSWER:
            low.append(text)
        elif answer >= _HIGH_ANSWER:
            high.append(text)
    return ContextInquiry(
        direction_slug=inquiry.direction_slug,
        readiness=inquiry.readiness,
        fit_summary=inquiry.fit_summary,
        note=inquiry.note,
        low_signals=low,
        high_signals=high,
    )


def _context_directions(analysis: AnalysisResult | None) -> list[ContextDirection]:
    if analysis is None:
        return []
    directions: list[ContextDirection] = []
    for d in analysis.directions or []:
        if not isinstance(d, dict) or "slug" not in d:
            continue
        directions.append(
            ContextDirection(
                slug=d.get("slug", ""),
                name=d.get("name", ""),
                match_score=int(d.get("match_score", 0)),
                description=d.get("description", ""),
                professions=list(d.get("professions", [])),
                skills_needed=list(d.get("skills_needed", [])),
                subjects_to_develop=list(d.get("subjects_to_develop", [])),
                first_steps=list(d.get("first_steps", [])),
            )
        )
    return directions


async def build_student_context(
    assessment_id: uuid.UUID,
    db: AsyncSession,
    *,
    inquiry_slug: str | None = None,
) -> StudentContext | None:
    """Assemble the full context for an assessment, or None if it doesn't exist.

    `inquiry_slug` attaches the stored inquiry outcome for that direction — the
    direction roadmap needs it; report and goal roadmap don't."""
    assessment = (
        await db.execute(select(Assessment).where(Assessment.id == assessment_id))
    ).scalar_one_or_none()
    if assessment is None:
        return None

    profile = (
        await db.execute(select(Profile).where(Profile.id == assessment.profile_id))
    ).scalar_one_or_none()
    if profile is None:
        return None

    analysis = (
        await db.execute(
            select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
        )
    ).scalar_one_or_none()

    artifact_rows = (
        await db.execute(select(Artifact).where(Artifact.profile_id == profile.id))
    ).scalars().all()
    artifacts = [ContextArtifact(type=a.type.value, value=a.value) for a in artifact_rows]

    inquiry = None
    if inquiry_slug is not None:
        inquiry = (
            await db.execute(
                select(DirectionInquiry).where(
                    DirectionInquiry.assessment_id == assessment_id,
                    DirectionInquiry.direction_slug == inquiry_slug,
                )
            )
        ).scalar_one_or_none()

    # Surface the raw signals that normalize_scores drops.
    raw_scores = await assessment_service.get_raw_scores(assessment_id, db)
    total_scores = scoring_service.normalize_scores(raw_scores)

    return StudentContext(
        name=profile.name,
        age=profile.age,
        age_group=profile.age_group.value,
        grade=profile.grade,
        city=profile.city,
        country=profile.country,
        language=profile.language,
        subjects_liked=list(profile.subjects_liked or []),
        subjects_disliked=list(profile.subjects_disliked or []),
        subjects_easy=list(profile.subjects_easy or []),
        subjects_hard=list(profile.subjects_hard or []),
        artifacts=artifacts,
        goal=assessment.goal.value,
        summary=analysis.summary if analysis else "",
        strengths=list(analysis.strengths) if analysis else [],
        interests_map=dict(analysis.interests_map) if analysis else {},
        thinking_style=dict(analysis.thinking_style) if analysis else {},
        motivation=list(analysis.motivation) if analysis else [],
        wellbeing_zones=list(analysis.wellbeing_zones) if analysis else [],
        growth_areas=ai_service.build_growth_areas(total_scores),
        values=scoring_service.extract_values(raw_scores),
        goal_clarification=scoring_service.extract_goal_signals(raw_scores),
        university_preferences=scoring_service.extract_preferences(raw_scores),
        directions=_context_directions(analysis),
        inquiry=_context_inquiry(inquiry),
    )
