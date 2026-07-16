import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact import Artifact
from app.models.assessment import Assessment
from app.models.profile import Profile
from app.schemas.student_context import (
    ContextArtifact,
    StudentContext,
)


async def build_student_context(
    assessment_id: uuid.UUID,
    db: AsyncSession,
    *,
    inquiry_slug: str | None = None,
) -> StudentContext | None:
    """Assemble the context for an assessment, or None if it doesn't exist."""
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

    artifact_rows = (
        await db.execute(select(Artifact).where(Artifact.profile_id == profile.id))
    ).scalars().all()
    artifacts = [ContextArtifact(type=a.type.value, value=a.value) for a in artifact_rows]

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
        summary="",
        strengths=[],
        interests_map={},
        thinking_style={},
        motivation=[],
        wellbeing_zones=[],
        growth_areas={},
        values={},
        goal_clarification={},
        university_preferences={},
        directions=[],
        inquiry=None,
    )
