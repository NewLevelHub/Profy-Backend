import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.profile import AgeGroup, Profile


async def create_assessment(
    profile_id: uuid.UUID, goal: AssessmentGoal, db: AsyncSession
) -> Assessment:
    profile_result = await db.execute(select(Profile).where(Profile.id == profile_id))
    profile = profile_result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    if goal == AssessmentGoal.university and profile.age_group != AgeGroup.senior:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Goal 'university' is only available for senior age group",
        )

    existing_result = await db.execute(
        select(Assessment).where(
            Assessment.profile_id == profile_id,
            Assessment.status == AssessmentStatus.in_progress,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        return existing

    assessment = Assessment(
        profile_id=profile_id,
        goal=goal,
        status=AssessmentStatus.in_progress,
        current_block=0,
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)
    return assessment


async def get_current_assessment(profile_id: uuid.UUID, db: AsyncSession) -> Assessment | None:
    result = await db.execute(
        select(Assessment).where(
            Assessment.profile_id == profile_id,
            Assessment.status == AssessmentStatus.in_progress,
        )
    )
    return result.scalar_one_or_none()
