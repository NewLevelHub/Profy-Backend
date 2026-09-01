import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.development_plan import (
    DevelopmentPlanResponse,
    GenerateDevelopmentPlanRequest,
)
from app.services import development_plan_service

router = APIRouter(tags=["development-plan"])


@router.post("", response_model=DevelopmentPlanResponse)
async def generate_plan(
    data: GenerateDevelopmentPlanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DevelopmentPlanResponse:
    return await development_plan_service.generate_development_plan(
        data.assessment_id, data.program_id, current_user.id, db
    )


@router.get("/{assessment_id}/{program_id}", response_model=DevelopmentPlanResponse)
async def get_plan(
    assessment_id: uuid.UUID,
    program_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DevelopmentPlanResponse:
    plan = await development_plan_service.get_development_plan(
        assessment_id, program_id, current_user.id, db
    )
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return plan
