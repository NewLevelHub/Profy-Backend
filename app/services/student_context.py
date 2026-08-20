"""Assemble a complete StudentContext from stored data.

Single source of truth for "everything we know about this student" — profile,
chosen goal, and the stored RIASEC report (profile/code/strengths/weaknesses/
careers), plus the safe display-ready Big Five/motivation layer (personality_*/
thinking_style/motivation_*; the raw admin-only scores stay out, see
StudentContext). Consumed by the roadmap builder and direction-inquiry LLM
prompts.
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
    ContextCareer,
    ContextInquiry,
    StudentContext,
)
from app.services import assessment_shared

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


def _context_careers(analysis: AnalysisResult | None) -> list[ContextCareer]:
    if analysis is None:
        return []
    careers: list[ContextCareer] = []
    for c in analysis.careers or []:
        if not isinstance(c, dict) or "slug" not in c:
            continue
        careers.append(
            ContextCareer(
                slug=c.get("slug", ""),
                name=c.get("name", ""),
                holland_code=c.get("holland_code", ""),
                match_score=int(c.get("match_score", 0)),
                description=c.get("description", ""),
                professions=list(c.get("professions", [])),
                skills_needed=list(c.get("skills_needed", [])),
                subjects_to_develop=list(c.get("subjects_to_develop", [])),
                first_steps=list(c.get("first_steps", [])),
            )
        )
    return careers


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

    # ТЗ §10.3 soft downgrade (middle + "university" -> "profession") must
    # hold for generation, not just the goal-overlay banner — see
    # `assessment_shared.get_effective_goal`. Every prompt reading
    # `StudentContext.goal` (goal-roadmap, direction-roadmap, direction
    # inquiry) sees the effective goal, never the raw stored one.
    effective_goal = assessment_shared.get_effective_goal(profile.age_group, assessment.goal)

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
        goal=effective_goal.value,
        summary=analysis.summary if analysis else "",
        profile=dict(analysis.profile) if analysis else {},
        code=list(analysis.code) if analysis else [],
        strengths=list(analysis.strengths) if analysis else [],
        weaknesses=list(analysis.weaknesses) if analysis else [],
        personality_profile=dict(analysis.personality_profile) if analysis else {},
        personality_notes=dict(analysis.personality_notes) if analysis else {},
        thinking_style=dict(analysis.thinking_style) if analysis else {},
        motivation_top=list(analysis.motivation_top) if analysis else [],
        motivation_highlights=list(analysis.motivation_highlights) if analysis else [],
        careers=_context_careers(analysis),
        inquiry=_context_inquiry(inquiry),
    )
