import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_student_user
from app.models.assessment import AssessmentGoal
from app.models.user import User
from app.schemas.assessment import AssessmentCreateRequest, AssessmentResponse
from app.schemas.response import SubmitAnswersRequest, SubmitAnswersResponse
from app.services import assessment_service
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
    current_user: User = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_db),
) -> AssessmentResponse:
    profile_id = await _require_profile_id(current_user, db)
    return await assessment_service.create_assessment(profile_id, data.goal, db)


@router.get("/current", response_model=AssessmentResponse)
async def get_current_assessment(
    current_user: User = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_db),
) -> AssessmentResponse:
    profile_id = await _require_profile_id(current_user, db)
    assessment = await assessment_service.get_current_assessment(profile_id, db)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active assessment found")
    return assessment


@router.post("/{assessment_id}/answers", response_model=SubmitAnswersResponse)
async def submit_answers(
    assessment_id: uuid.UUID,
    data: SubmitAnswersRequest,
    current_user: User = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_db),
) -> SubmitAnswersResponse:
    profile_id = await _require_profile_id(current_user, db)
    return await assessment_service.submit_answers(
        assessment_id, data.answers, profile_id, db
    )


class UpdateGoalRequest(BaseModel):
    goal: AssessmentGoal
    secondary_goals: list[AssessmentGoal] = []


@router.patch("/{assessment_id}/goal", response_model=AssessmentResponse)
async def update_goal(
    assessment_id: uuid.UUID,
    data: UpdateGoalRequest,
    current_user: User = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_db),
) -> AssessmentResponse:
    profile_id = await _require_profile_id(current_user, db)
    return await assessment_service.update_assessment_goal(
        assessment_id, data.goal, data.secondary_goals, profile_id, db
    )

