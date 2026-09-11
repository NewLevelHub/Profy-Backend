"""Psychologist router — every student, their reports, and notes.

Mounted at `/api/v1/psychologist`. Psychologists never share admin routes;
access is gated with `require_role(UserRole.psychologist)`. There is no
assignment step — a psychologist sees every student (PRO-321 rework).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.user import User, UserRole
from app.schemas.psychologist import (
    PsychologistNoteCreate,
    PsychologistNoteItem,
    PsychologistNoteUpdate,
    PsychologistStudentDetailResponse,
    PsychologistStudentListItem,
)
from app.schemas.result_v2 import ResultResponseV2, ResultV2Schema
from app.services import psychologist_service

router = APIRouter(tags=["psychologist"])

_require_psychologist = require_role(UserRole.psychologist)


@router.get("/students", response_model=list[PsychologistStudentListItem])
async def list_students(
    current_user: User = Depends(_require_psychologist),
    db: AsyncSession = Depends(get_db),
) -> list[PsychologistStudentListItem]:
    return await psychologist_service.list_students(db)


@router.get("/students/{student_id}", response_model=PsychologistStudentDetailResponse)
async def get_student(
    student_id: uuid.UUID,
    current_user: User = Depends(_require_psychologist),
    db: AsyncSession = Depends(get_db),
) -> PsychologistStudentDetailResponse:
    try:
        return await psychologist_service.get_student_detail(db, student_id=student_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/students/{student_id}/result/{assessment_id}",
    response_model=ResultV2Schema,
)
async def get_student_report(
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
    current_user: User = Depends(_require_psychologist),
    db: AsyncSession = Depends(get_db),
) -> ResultResponseV2:
    """The student's full RIASEC / Big Five / (Люшер) психоэмоциональный /
    достоверность report — psych-block sections included because the viewer
    is a psychologist."""
    try:
        return await psychologist_service.get_student_report(
            db,
            student_id=student_id,
            assessment_id=assessment_id,
            viewer=current_user,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/students/{student_id}/notes",
    response_model=list[PsychologistNoteItem],
)
async def list_student_notes(
    student_id: uuid.UUID,
    current_user: User = Depends(_require_psychologist),
    db: AsyncSession = Depends(get_db),
) -> list[PsychologistNoteItem]:
    return await psychologist_service.list_notes(
        db, psychologist_id=current_user.id, student_id=student_id
    )


@router.post(
    "/students/{student_id}/notes",
    response_model=PsychologistNoteItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_student_note(
    student_id: uuid.UUID,
    body: PsychologistNoteCreate,
    current_user: User = Depends(_require_psychologist),
    db: AsyncSession = Depends(get_db),
) -> PsychologistNoteItem:
    try:
        return await psychologist_service.create_note(
            db,
            psychologist_id=current_user.id,
            student_id=student_id,
            body=body,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/notes/{note_id}", response_model=PsychologistNoteItem)
async def update_note(
    note_id: uuid.UUID,
    body: PsychologistNoteUpdate,
    current_user: User = Depends(_require_psychologist),
    db: AsyncSession = Depends(get_db),
) -> PsychologistNoteItem:
    try:
        return await psychologist_service.update_note(
            db,
            psychologist_id=current_user.id,
            note_id=note_id,
            body=body,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: uuid.UUID,
    current_user: User = Depends(_require_psychologist),
    db: AsyncSession = Depends(get_db),
):
    try:
        await psychologist_service.delete_note(
            db, psychologist_id=current_user.id, note_id=note_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
