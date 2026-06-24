import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.assessment import Assessment
from app.models.profile import Profile
from app.models.user import User
from app.schemas.result import AnalysisResultResponse
from app.services import report_service

router = APIRouter(tags=["result"])


class GenerateReportRequest(BaseModel):
    assessment_id: uuid.UUID


async def _require_assessment_access(
    assessment_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> None:
    row = await db.execute(
        select(Assessment, Profile.user_id)
        .join(Profile, Assessment.profile_id == Profile.id)
        .where(Assessment.id == assessment_id)
    )
    row_data = row.one_or_none()
    if row_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found"
        )
    _, owner_user_id = row_data
    if owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )


@router.post("/generate", response_model=AnalysisResultResponse)
async def generate_report(
    data: GenerateReportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalysisResultResponse:
    await _require_assessment_access(data.assessment_id, current_user, db)
    return await report_service.build_report(data.assessment_id, db)


@router.get("/{assessment_id}", response_model=AnalysisResultResponse)
async def get_report(
    assessment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalysisResultResponse:
    await _require_assessment_access(assessment_id, current_user, db)
    result = await report_service.get_report(assessment_id, db)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report not found"
        )
    return result
