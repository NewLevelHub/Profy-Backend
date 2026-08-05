import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.assessment import Assessment
from app.models.profile import Profile
from app.models.user import User
from app.schemas.motivation import (
    MotivationTripletResponse,
    SubmitMotivationRequest,
    SubmitMotivationResponse,
)
from app.services import motivation_service
from app.services.profile_service import get_profile

router = APIRouter(tags=["motivation"])


async def _require_profile_id(current_user: User, db: AsyncSession) -> uuid.UUID:
    profile = await get_profile(current_user.id, db)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile.id


@router.get("/{assessment_id}/motivation-triplets", response_model=list[MotivationTripletResponse])
async def get_motivation_triplets(
    assessment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MotivationTripletResponse]:
    row_result = await db.execute(
        select(Assessment, Profile.user_id)
        .join(Profile, Assessment.profile_id == Profile.id)
        .where(Assessment.id == assessment_id)
    )
    row = row_result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    _, owner_user_id = row
    if owner_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    grouped = await motivation_service.triplets(db)
    return [
        MotivationTripletResponse(triplet_index=triplet_index, statements=statements)
        for triplet_index, statements in sorted(grouped.items())
    ]


@router.post("/{assessment_id}/motivation-answers", response_model=SubmitMotivationResponse)
async def submit_motivation_answers(
    assessment_id: uuid.UUID,
    data: SubmitMotivationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubmitMotivationResponse:
    profile_id = await _require_profile_id(current_user, db)
    return await motivation_service.submit_motivation_answers(
        assessment_id, data.answers, profile_id, db
    )
