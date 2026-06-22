import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.answer import AnswersBulkRequest, AnswersResponse
from app.schemas.assessment import AssessmentCreateRequest, AssessmentResponse
from app.services import answer_service, assessment_service
from app.services.profile_service import get_profile

router = APIRouter(tags=["assessment"])


async def _require_profile_id(current_user: User, db: AsyncSession):
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


@router.post("/{assessment_id}/answers", response_model=AnswersResponse)
async def submit_answers(
    assessment_id: uuid.UUID,
    data: AnswersBulkRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnswersResponse:
    profile_id = await _require_profile_id(current_user, db)
    return await answer_service.save_answers(assessment_id, data.block, data.answers, profile_id, db)
