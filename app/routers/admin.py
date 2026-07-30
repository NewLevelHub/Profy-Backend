import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_admin_user
from app.models.user import User
from app.schemas.admin import (
    AdminAssessmentDetailResponse,
    AdminFeedbackListResponse,
    AdminFeedbackStatsResponse,
    AdminUserDetailResponse,
    AdminUserListResponse,
    AdminStatsResponse,
)
from app.services import admin_service, product_feedback_service

router = APIRouter(tags=["admin"])


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.list_users(db, page=page, limit=limit, search=search)


@router.get("/stats", response_model=AdminStatsResponse)
async def get_admin_stats(
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.get_admin_stats(db)



@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)
async def get_user_detail(
    user_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    detail = await admin_service.get_user_detail(db, user_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return detail


@router.get("/assessments/{assessment_id}", response_model=AdminAssessmentDetailResponse)
async def get_assessment_detail(
    assessment_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    detail = await admin_service.get_assessment_detail(db, assessment_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    return detail


@router.get("/feedback", response_model=AdminFeedbackListResponse)
async def list_feedback(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    rating: str | None = Query(default=None),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await product_feedback_service.list_feedback(db, page=page, limit=limit, rating=rating)


@router.get("/feedback/stats", response_model=AdminFeedbackStatsResponse)
async def get_feedback_stats(
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await product_feedback_service.get_feedback_stats(db)
