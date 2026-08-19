from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.artifact import Artifact
from app.models.profile import Profile
from app.models.user import User
from app.schemas.artifact import ArtifactItem
from app.schemas.profile import (
    ProfileCreateRequest,
    ProfileResponse,
    ProfileUpdateRequest,
)
from app.services import artifact_service, profile_service

router = APIRouter(tags=["profile"])


def _to_response(profile: Profile, artifacts: list[Artifact]) -> ProfileResponse:
    return ProfileResponse.model_validate(profile).model_copy(
        update={"artifacts": [ArtifactItem(type=a.type, value=a.value) for a in artifacts]}
    )


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    data: ProfileCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Create the caller's Profile, optionally saving their artifact
    selections in the same request/transaction (`data.artifacts`).

    Both writes commit together: if artifact persistence fails after the
    profile insert has been flushed, nothing is committed and the whole
    request rolls back — no half-created profile with no artifacts. Clients
    that omit `artifacts` (or still call the old two-step flow) are
    unaffected: this is purely additive to the existing contract.
    """
    try:
        profile = await profile_service.create_profile(current_user.id, data, db, commit=False)

        saved_artifacts: list[Artifact] = []
        if data.artifacts is not None:
            saved_artifacts = await artifact_service.save_artifacts(
                profile.id, data.artifacts, db, commit=False
            )

        await db.commit()
        await db.refresh(profile)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return _to_response(profile, saved_artifacts)


@router.get("", response_model=ProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    profile = await profile_service.get_profile(current_user.id, db)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    artifacts = await artifact_service.get_artifacts(profile.id, db)
    return _to_response(profile, artifacts)


@router.put("", response_model=ProfileResponse)
async def update_profile(
    data: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Update the caller's Profile, optionally replacing their artifacts in
    the same request/transaction (`data.artifacts`) — same combined-write
    contract as POST. Omitting `artifacts` leaves them untouched; the
    response still echoes the current set either way.
    """
    try:
        profile, artifacts = await profile_service.update_profile(current_user.id, data, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return _to_response(profile, artifacts)
