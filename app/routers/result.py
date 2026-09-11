import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.errors import AppError
from app.models.assessment import Assessment
from app.models.profile import Profile
from app.models.user import User
from app.schemas.feedback import ProductFeedbackCreate, ProductFeedbackResponse
from app.schemas.goal_overlay import GoalOverlayResponse
from app.schemas.result_v2 import ResultResponseV2, ResultV2Schema
from app.services import feedback_service, report_service

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


@router.post("/generate", response_model=ResultV2Schema)
async def generate_report(
    data: GenerateReportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResultResponseV2:
    await _require_assessment_access(data.assessment_id, current_user, db)
    return await report_service.build_report(data.assessment_id, db)


@router.get("/{assessment_id}", response_model=ResultV2Schema)
async def get_report(
    assessment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResultResponseV2:
    await _require_assessment_access(assessment_id, current_user, db)
    result, outcome = await report_service.resolve_report(assessment_id, db)
    if result is None:
        # KZ-406: a report may exist in another locale (student switched
        # language) — signal that so the client shows a "generating" state
        # and POSTs /generate, rather than treating it as "no report".
        if outcome is report_service.ReportLookup.LOCALE_NOT_GENERATED:
            raise AppError(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="report_locale_not_generated",
                detail="Отчёт на выбранном языке ещё не создан",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report not found"
        )
    return result


@router.post("/feedback", response_model=ProductFeedbackResponse)
async def submit_feedback(
    data: ProductFeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProductFeedbackResponse:
    await _require_assessment_access(data.assessment_id, current_user, db)
    return await feedback_service.submit_feedback(current_user.id, data, db)


@router.get("/{assessment_id}/goal-context", response_model=GoalOverlayResponse)
async def get_goal_context(
    assessment_id: uuid.UUID,
    program_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GoalOverlayResponse:
    from app.services import goal_overlay_service
    await _require_assessment_access(assessment_id, current_user, db)
    return await goal_overlay_service.get_or_create_goal_overlay(
        assessment_id, db, program_id=program_id
    )

