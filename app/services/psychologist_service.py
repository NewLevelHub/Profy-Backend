"""Psychologist access to students, their reports, and notes.

Scope decision (PRO-321 rework): a psychologist sees **every** student — no
assignment step, one implicit psychologist↔all-students relation. Student
list/detail/report and notes are gated only by `require_role(psychologist)`;
a target that isn't an existing student → not-found (404), never 403.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment
from app.models.profile import Profile
from app.models.psychologist_note import PsychologistNote
from app.models.user import User, UserRole
from app.schemas.admin import AdminUserDetailResponse
from app.schemas.psychologist import (
    PsychologistAssessmentSummary,
    PsychologistNoteCreate,
    PsychologistNoteItem,
    PsychologistNoteUpdate,
    PsychologistStudentDetailResponse,
    PsychologistStudentListItem,
)
from app.schemas.result_v2 import ResultResponseV2
from app.services import admin_service


async def _require_student(db: AsyncSession, student_id: uuid.UUID) -> User:
    user = await db.get(User, student_id)
    if user is None or user.role != UserRole.student:
        raise ValueError("Student not found")
    return user


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


async def list_students(db: AsyncSession) -> list[PsychologistStudentListItem]:
    query = (
        select(
            User.id,
            User.email,
            User.created_at,
            Profile.name,
            Profile.age_group,
        )
        .outerjoin(Profile, Profile.user_id == User.id)
        .where(User.role == UserRole.student)
        .order_by(User.created_at.desc())
    )
    rows = (await db.execute(query)).all()
    return [
        PsychologistStudentListItem(
            id=row.id,
            email=row.email,
            profile_name=row.name,
            age_group=row.age_group.value if row.age_group is not None else None,
            registered_at=row.created_at,
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


async def get_student_detail(
    db: AsyncSession, *, student_id: uuid.UUID
) -> PsychologistStudentDetailResponse:
    await _require_student(db, student_id)
    detail = await admin_service.get_user_detail(db, student_id)
    if detail is None:
        raise ValueError("Student not found")
    return _to_psychologist_detail(detail)


async def get_student_report(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
    viewer: User,
) -> ResultResponseV2:
    """The student's full /result v2 report. `viewer` is the psychologist, so
    report_service.psych_sections_for → True and the validity / psychoemotional
    / mac sections are attached (a student never sees these on their own
    /result)."""
    await _require_student(db, student_id)

    owns = await db.execute(
        select(Assessment.id)
        .join(Profile, Assessment.profile_id == Profile.id)
        .where(Assessment.id == assessment_id, Profile.user_id == student_id)
    )
    if owns.scalar_one_or_none() is None:
        raise ValueError("Assessment not found")

    # Imported here to avoid a module-level import cycle (report_service pulls
    # in most of the service layer).
    from app.services import report_service

    return await report_service.build_report(assessment_id, db, viewer=viewer)


async def create_note(
    db: AsyncSession,
    *,
    psychologist_id: uuid.UUID,
    student_id: uuid.UUID,
    body: PsychologistNoteCreate,
) -> PsychologistNote:
    await _require_student(db, student_id)
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
