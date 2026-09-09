"""Psychologist router — assigned students only (PRO-327 / Milestone 2).

Mounted at `/api/v1/psychologist`. Psychologists never share admin routes;
access is gated with `require_role(UserRole.psychologist)`.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.user import User, UserRole
from app.schemas.psychologist import (
    PsychologistStudentDetailResponse,
    PsychologistStudentListItem,
)
from app.services import psychologist_service

router = APIRouter(tags=["psychologist"])

_require_psychologist = require_role(UserRole.psychologist)


@router.get("/students", response_model=list[PsychologistStudentListItem])
async def list_students(
    current_user: User = Depends(_require_psychologist),
    db: AsyncSession = Depends(get_db),
) -> list[PsychologistStudentListItem]:
    return await psychologist_service.list_assigned_students(db, current_user.id)


@router.get("/students/{student_id}", response_model=PsychologistStudentDetailResponse)
async def get_student(
    student_id: uuid.UUID,
    current_user: User = Depends(_require_psychologist),
    db: AsyncSession = Depends(get_db),
) -> PsychologistStudentDetailResponse:
    try:
        return await psychologist_service.get_assigned_student_detail(
            db, psychologist_id=current_user.id, student_id=student_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
