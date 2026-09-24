import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_student_user
from app.errors import AppError
from app.models.analysis_result import ReviewStatus
from app.models.assessment import Assessment
from app.models.profile import Profile
from app.models.user import User
from app.schemas.feedback import ProductFeedbackCreate, ProductFeedbackResponse
from app.schemas.result_v2 import (
    ResultOrPendingSchema,
    ResultPendingReviewResponse,
    ResultResponseV2,
)
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


@router.post("/generate", response_model=ResultOrPendingSchema)
async def generate_report(
    data: GenerateReportRequest,
    current_user: User = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_db),
) -> ResultResponseV2 | ResultPendingReviewResponse:
    await _require_assessment_access(data.assessment_id, current_user, db)
    report = await report_service.build_report(
        data.assessment_id, db, viewer=current_user
    )
    review_status = await report_service.get_review_status(data.assessment_id, db)
    # Fail closed: anything but an explicit `published` stays hidden.
    if review_status != ReviewStatus.published:
        return ResultPendingReviewResponse(assessment_id=data.assessment_id)
    return report


@router.get("/{assessment_id}", response_model=ResultOrPendingSchema)
async def get_report(
    assessment_id: uuid.UUID,
    current_user: User = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_db),
) -> ResultResponseV2 | ResultPendingReviewResponse:
    await _require_assessment_access(assessment_id, current_user, db)
    # Gate before resolving the report — an unpublished report must never be
    # shaped or read from the cache for a student. The review status is one
    # per assessment, shared by every locale row (KZ-405), so it is checked
    # before the per-locale lookup below.
    review_status = await report_service.get_review_status(assessment_id, db)
    if review_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report not found"
        )
    if review_status != ReviewStatus.published:
        return ResultPendingReviewResponse(assessment_id=assessment_id)
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
    current_user: User = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_db),
) -> ProductFeedbackResponse:
    await _require_assessment_access(data.assessment_id, current_user, db)
    return await feedback_service.submit_feedback(current_user.id, data, db)
