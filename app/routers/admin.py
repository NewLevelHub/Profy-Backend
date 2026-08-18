import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_admin_user
from app.models.user import User
from app.schemas.admin import (
    AdminAssessmentDetailResponse,
    AdminUserDetailResponse,
    AdminUserListResponse,
)
from app.schemas.admin_university import (
    AdminUniversityListResponse,
    AdminUniversityDetail,
    AdminUniversityUpdateRequest,
    AdminProgramDetail,
    AdminProgramUpdateRequest,
)
from app.services import admin_service, admin_university_service, university_service

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


@router.get("/universities", response_model=AdminUniversityListResponse)
async def list_universities(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_university_service.list_universities(db, page=page, limit=limit, search=search)


@router.get("/universities/{university_id}", response_model=AdminUniversityDetail)
async def get_university_detail(
    university_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    detail = await admin_university_service.get_university_detail(db, university_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="University not found")
    return detail


@router.patch("/universities/{university_id}", response_model=AdminUniversityDetail)
async def update_university(
    university_id: uuid.UUID,
    data: AdminUniversityUpdateRequest,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_university_service.update_university(db, university_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/programs/{program_id}", response_model=AdminProgramDetail)
async def get_program_detail(
    program_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await university_service.get_program_by_id(db, program_id)
    except HTTPException:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found")


@router.patch("/programs/{program_id}", response_model=AdminProgramDetail)
async def update_program(
    program_id: uuid.UUID,
    data: AdminProgramUpdateRequest,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_university_service.update_program(db, program_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
