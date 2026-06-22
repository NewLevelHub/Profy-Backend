import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import Profile, compute_age_group
from app.schemas.profile import ProfileCreateRequest, ProfileUpdateRequest


async def create_profile(user_id: uuid.UUID, data: ProfileCreateRequest, db: AsyncSession) -> Profile:
    existing = await db.execute(select(Profile).where(Profile.user_id == user_id))
    if existing.scalar_one_or_none() is not None:
        raise ValueError("Profile already exists for this user")

    profile = Profile(
        user_id=user_id,
        age_group=compute_age_group(data.age),
        **data.model_dump(),
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def get_profile(user_id: uuid.UUID, db: AsyncSession) -> Profile | None:
    result = await db.execute(select(Profile).where(Profile.user_id == user_id))
    return result.scalar_one_or_none()


async def update_profile(user_id: uuid.UUID, data: ProfileUpdateRequest, db: AsyncSession) -> Profile:
    result = await db.execute(select(Profile).where(Profile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise ValueError("Profile not found")

    updates = data.model_dump(exclude_none=True)
    for key, value in updates.items():
        setattr(profile, key, value)

    if "age" in updates:
        profile.age_group = compute_age_group(updates["age"])

    await db.commit()
    await db.refresh(profile)
    return profile
