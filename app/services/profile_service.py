import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact import Artifact
from app.models.certificate import Certificate
from app.models.profile import Profile, compute_age_group
from app.schemas.profile import ProfileCreateRequest, ProfileUpdateRequest
from app.services import artifact_service, certificate_service


async def create_profile(
    user_id: uuid.UUID,
    data: ProfileCreateRequest,
    db: AsyncSession,
    *,
    commit: bool = True,
) -> Profile:
    """Create the Profile row for `user_id`.

    `commit=False` lets a caller (e.g. the combined profile+artifacts create
    endpoint) flush the insert without ending the transaction, so it can be
    combined atomically with other writes and committed once at the end.
    Standalone callers keep the default `commit=True`, which is exactly the
    previous behavior.
    """
    existing = await db.execute(select(Profile).where(Profile.user_id == user_id))
    if existing.scalar_one_or_none() is not None:
        raise ValueError("Profile already exists for this user")

    # `artifacts`/`certificates` (if present) are handled by the caller via
    # artifact_service/certificate_service, not Profile columns — exclude
    # them before spreading onto the model. Everything else on the request
    # is a real Profile column and passes through untouched.
    profile_fields = data.model_dump(exclude={"artifacts", "certificates"})
    profile = Profile(
        user_id=user_id,
        age_group=compute_age_group(data.age),
        **profile_fields,
    )
    db.add(profile)
    if commit:
        await db.commit()
    else:
        await db.flush()
    await db.refresh(profile)
    return profile


async def get_profile(user_id: uuid.UUID, db: AsyncSession) -> Profile | None:
    result = await db.execute(select(Profile).where(Profile.user_id == user_id))
    return result.scalar_one_or_none()


async def update_profile(
    user_id: uuid.UUID, data: ProfileUpdateRequest, db: AsyncSession
) -> tuple[Profile, list[Artifact], list[Certificate]]:
    """Update the caller's Profile, optionally replacing their artifacts
    and/or certificates in the same transaction (`data.artifacts`,
    `data.certificates`) — mirrors `create_profile`'s combined-write
    contract. `None` for either means "leave that sub-resource untouched";
    the current set is still fetched so the response can embed it (see
    `ProfileResponse.artifacts`/`.certificates`), same as GET.
    """
    result = await db.execute(select(Profile).where(Profile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise ValueError("Profile not found")

    updates = data.model_dump(exclude={"artifacts", "certificates"}, exclude_none=True)
    for key, value in updates.items():
        setattr(profile, key, value)

    if "age" in updates:
        profile.age_group = compute_age_group(updates["age"])

    if data.artifacts is not None:
        artifacts = await artifact_service.save_artifacts(profile.id, data.artifacts, db, commit=False)
    else:
        artifacts = await artifact_service.get_artifacts(profile.id, db)

    if data.certificates is not None:
        certificates = await certificate_service.save_certificates(
            profile.id, data.certificates, db, commit=False
        )
    else:
        certificates = await certificate_service.get_certificates(profile.id, db)

    await db.commit()
    await db.refresh(profile)
    return profile, artifacts, certificates
