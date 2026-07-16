import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.axes import AXIS_CATALOG
from app.models.artifact import Artifact
from app.models.assessment import Assessment
from app.models.direction import Direction
from app.models.profile import Profile
from app.schemas.student_context import ContextArtifact, StudentContext

_AXIS_LABELS: dict[str, str] = {axis.code: axis.label_ru for axis in AXIS_CATALOG}
_STRENGTH_THRESHOLD = 1
_TOP_LEANING_COUNT = 5


async def build_student_context(
    assessment_id: uuid.UUID,
    db: AsyncSession,
    *,
    direction_slug: str | None = None,
) -> StudentContext | None:
    """Assemble the context for an assessment, or None if it doesn't exist.

    `direction_slug` is the direction the roadmap is being built for — its
    Direction.profile is what `strengths` is read off of.
    """
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

    session = assessment.session
    belief: dict[str, float] = session.belief if session else {}
    rejected_slugs: list[str] = list(session.rejected_leaves) if session else []
    top_slugs = [
        slug for slug, _ in sorted(belief.items(), key=lambda item: item[1], reverse=True)
    ][:_TOP_LEANING_COUNT]

    lookup_slugs = set(top_slugs) | set(rejected_slugs)
    if direction_slug:
        lookup_slugs.add(direction_slug)

    directions_by_slug: dict[str, Direction] = {}
    if lookup_slugs:
        rows = (
            await db.execute(select(Direction).where(Direction.slug.in_(lookup_slugs)))
        ).scalars().all()
        directions_by_slug = {d.slug: d for d in rows}

    leaning_directions = {
        directions_by_slug[slug].name: round(belief[slug], 3)
        for slug in top_slugs
        if slug in directions_by_slug
    }
    rejected_directions = [
        directions_by_slug[slug].name for slug in rejected_slugs if slug in directions_by_slug
    ]

    strengths: list[str] = []
    target_direction = directions_by_slug.get(direction_slug) if direction_slug else None
    if target_direction is not None:
        ranked_axes = sorted(
            (target_direction.profile or {}).items(), key=lambda item: item[1], reverse=True
        )
        strengths = [
            _AXIS_LABELS[code]
            for code, value in ranked_axes
            if value >= _STRENGTH_THRESHOLD and code in _AXIS_LABELS
        ]

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
        strengths=strengths,
        leaning_directions=leaning_directions,
        rejected_directions=rejected_directions,
    )
