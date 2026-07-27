import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.assessment import AssessmentCreateRequest, AssessmentResponse
from app.schemas.known_profession import (
    KnownProfessionFinalizeRequest,
    KnownProfessionFinalizeResponse,
)
from app.services import assessment_service, known_profession_service
from app.services.profile_service import get_profile

router = APIRouter(tags=["assessment"])


async def _require_profile_id(current_user: User, db: AsyncSession) -> uuid.UUID:
    profile = await get_profile(current_user.id, db)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile.id


@router.post("/start", response_model=AssessmentResponse)
async def start_assessment(
    data: AssessmentCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssessmentResponse:
    profile_id = await _require_profile_id(current_user, db)
    return await assessment_service.create_assessment(profile_id, data.goal, db)


@router.get("/current", response_model=AssessmentResponse)
async def get_current_assessment(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssessmentResponse:
    profile_id = await _require_profile_id(current_user, db)
    assessment = await assessment_service.get_current_assessment(profile_id, db)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active assessment found")
    return assessment


@router.post("/known-profession/finalize", response_model=KnownProfessionFinalizeResponse)
async def finalize_known_profession_quiz(
    data: KnownProfessionFinalizeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnownProfessionFinalizeResponse:
    """Finalizes the "Уже знаю, кем хочу стать" flow: scores the validation
    quiz and creates a completed, sessionless Assessment so /result and
    /roadmap work immediately — see known_profession_service."""
    profile_id = await _require_profile_id(current_user, db)
    assessment, percent, verdict = await known_profession_service.finalize(
        profile_id, data.direction_slug, data.answers, db
    )
    return KnownProfessionFinalizeResponse(
        assessment_id=assessment.id, percent=percent, verdict=verdict
    )
