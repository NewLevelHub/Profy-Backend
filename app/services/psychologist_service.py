"""Psychologist access to assigned students and notes (PRO-327 / PRO-330).

Student list/detail are assignment-gated. Notes use soft cutoff: create
requires an active assignment; list/update/delete of notes the psychologist
already owns do not — missing ownership → not-found (404), never 403.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.profile import Profile
from app.models.psychologist_assignment import PsychologistStudentAssignment
from app.models.psychologist_note import PsychologistNote
from app.models.user import User
from app.schemas.admin import AdminUserDetailResponse
from app.schemas.psychologist import (
    PsychologistAssessmentSummary,
    PsychologistNoteCreate,
    PsychologistNoteItem,
    PsychologistNoteUpdate,
    PsychologistStudentDetailResponse,
    PsychologistStudentListItem,
)
from app.services import admin_service


async def _require_assigned_student(
    db: AsyncSession,
    *,
    psychologist_id: uuid.UUID,
    student_id: uuid.UUID,
) -> PsychologistStudentAssignment:
    result = await db.execute(
        select(PsychologistStudentAssignment).where(
            PsychologistStudentAssignment.psychologist_id == psychologist_id,
            PsychologistStudentAssignment.student_id == student_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise ValueError("Student not found")
    return assignment


async def _require_own_note(
    db: AsyncSession,
    *,
    psychologist_id: uuid.UUID,
    note_id: uuid.UUID,
) -> PsychologistNote:
    note = await db.get(PsychologistNote, note_id)
    if note is None or note.psychologist_id != psychologist_id:
        raise ValueError("Note not found")
    return note


async def list_assigned_students(
    db: AsyncSession, psychologist_id: uuid.UUID
) -> list[PsychologistStudentListItem]:
    student = aliased(User)
    query = (
        select(
            student.id,
            student.email,
            Profile.name,
            Profile.age_group,
            PsychologistStudentAssignment.created_at,
        )
        .join(student, student.id == PsychologistStudentAssignment.student_id)
        .outerjoin(Profile, Profile.user_id == student.id)
        .where(PsychologistStudentAssignment.psychologist_id == psychologist_id)
        .order_by(PsychologistStudentAssignment.created_at.desc())
    )
    rows = (await db.execute(query)).all()
    return [
        PsychologistStudentListItem(
            id=row.id,
            email=row.email,
            profile_name=row.name,
            age_group=row.age_group.value if row.age_group is not None else None,
            assigned_at=row.created_at,
        )
        for row in rows
    ]


def _to_psychologist_detail(
    detail: AdminUserDetailResponse,
) -> PsychologistStudentDetailResponse:
    return PsychologistStudentDetailResponse(
        id=detail.id,
        email=detail.email,
        is_verified=detail.is_verified,
        is_active=detail.is_active,
        created_at=detail.created_at,
        profile=detail.profile,
        artifacts=detail.artifacts,
        assessments=[
            PsychologistAssessmentSummary(
                id=a.id,
                goal=a.goal,
                status=a.status,
                answered_count=a.answered_count,
                total_questions=a.total_questions,
                created_at=a.created_at,
                completed_at=a.completed_at,
                has_result=a.has_result,
                has_roadmap=a.has_roadmap,
            )
            for a in detail.assessments
        ],
    )


async def get_assigned_student_detail(
    db: AsyncSession,
    *,
    psychologist_id: uuid.UUID,
    student_id: uuid.UUID,
) -> PsychologistStudentDetailResponse:
    await _require_assigned_student(
        db, psychologist_id=psychologist_id, student_id=student_id
    )
    detail = await admin_service.get_user_detail(db, student_id)
    if detail is None:
        # Assignment pointed at a deleted user mid-request — treat as missing.
        raise ValueError("Student not found")
    return _to_psychologist_detail(detail)


async def create_note(
    db: AsyncSession,
    *,
    psychologist_id: uuid.UUID,
    student_id: uuid.UUID,
    body: PsychologistNoteCreate,
) -> PsychologistNote:
    # Soft cutoff: new notes require an active assignment.
    await _require_assigned_student(
        db, psychologist_id=psychologist_id, student_id=student_id
    )
    note = PsychologistNote(
        psychologist_id=psychologist_id,
        student_id=student_id,
        content=body.content,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


async def list_notes(
    db: AsyncSession,
    *,
    psychologist_id: uuid.UUID,
    student_id: uuid.UUID,
) -> list[PsychologistNoteItem]:
    # Soft cutoff: listing does not require a current assignment — only
    # notes owned by this psychologist for this student are returned.
    result = await db.execute(
        select(PsychologistNote)
        .where(
            PsychologistNote.psychologist_id == psychologist_id,
            PsychologistNote.student_id == student_id,
        )
        .order_by(PsychologistNote.created_at.desc())
    )
    return [
        PsychologistNoteItem.model_validate(row) for row in result.scalars().all()
    ]


async def update_note(
    db: AsyncSession,
    *,
    psychologist_id: uuid.UUID,
    note_id: uuid.UUID,
    body: PsychologistNoteUpdate,
) -> PsychologistNote:
    note = await _require_own_note(
        db, psychologist_id=psychologist_id, note_id=note_id
    )
    note.content = body.content
    await db.commit()
    await db.refresh(note)
    return note


async def delete_note(
    db: AsyncSession,
    *,
    psychologist_id: uuid.UUID,
    note_id: uuid.UUID,
) -> None:
    note = await _require_own_note(
        db, psychologist_id=psychologist_id, note_id=note_id
    )
    await db.delete(note)
    await db.commit()
