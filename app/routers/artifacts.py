from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_student_user
from app.models.user import User
from app.schemas.artifact import ArtifactItem, ArtifactsBulkRequest, ArtifactsResponse
from app.services import artifact_service
from app.services.profile_service import get_profile

router = APIRouter(tags=["artifacts"])


async def _require_profile_id(current_user: User, db: AsyncSession) -> object:
    profile = await get_profile(current_user.id, db)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile.id


@router.post("", response_model=ArtifactsResponse)
async def save_artifacts(
    data: ArtifactsBulkRequest,
    current_user: User = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_db),
) -> ArtifactsResponse:
    profile_id = await _require_profile_id(current_user, db)
    artifacts = await artifact_service.save_artifacts(profile_id, data.items, db)
    return ArtifactsResponse(items=[ArtifactItem(type=a.type, value=a.value) for a in artifacts])


@router.get("", response_model=ArtifactsResponse)
async def get_artifacts(
    current_user: User = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_db),
) -> ArtifactsResponse:
    profile_id = await _require_profile_id(current_user, db)
    artifacts = await artifact_service.get_artifacts(profile_id, db)
    return ArtifactsResponse(items=[ArtifactItem(type=a.type, value=a.value) for a in artifacts])
