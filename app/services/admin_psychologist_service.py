"""Admin CRUD for psychologist↔student assignments (PRO-326 / Milestone 2).

Role checks live here, not in the DB — `PsychologistStudentAssignment` only
enforces the unique (psychologist_id, student_id) pair. See
docs/user-roles-integration-plan.md Milestone 2.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.psychologist_assignment import PsychologistStudentAssignment
from app.models.user import User, UserRole
from app.schemas.admin import (
    PsychologistAssignmentCreate,
    PsychologistAssignmentItem,
    PsychologistAssignmentListResponse,
)


async def create_assignment(
    db: AsyncSession, body: PsychologistAssignmentCreate
) -> PsychologistStudentAssignment:
    psychologist = await db.get(User, body.psychologist_id)
    if psychologist is None:
        raise ValueError("Psychologist not found")
    if psychologist.role != UserRole.psychologist:
        raise ValueError("psychologist_id must refer to a user with role=psychologist")

    student = await db.get(User, body.student_id)
    if student is None:
        raise ValueError("Student not found")
    if student.role != UserRole.student:
        raise ValueError("student_id must refer to a user with role=student")

    existing = await db.execute(
        select(PsychologistStudentAssignment).where(
            PsychologistStudentAssignment.psychologist_id == body.psychologist_id,
            PsychologistStudentAssignment.student_id == body.student_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError("Assignment already exists")

    assignment = PsychologistStudentAssignment(
        psychologist_id=body.psychologist_id,
        student_id=body.student_id,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    return assignment


async def list_assignments(
    db: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    psychologist_id: uuid.UUID | None = None,
    student_id: uuid.UUID | None = None,
) -> PsychologistAssignmentListResponse:
    filters = []
    if psychologist_id is not None:
        filters.append(PsychologistStudentAssignment.psychologist_id == psychologist_id)
    if student_id is not None:
        filters.append(PsychologistStudentAssignment.student_id == student_id)

    count_query = select(func.count()).select_from(PsychologistStudentAssignment)
    if filters:
        count_query = count_query.where(*filters)
    total = (await db.execute(count_query)).scalar_one()

    query = (
        select(PsychologistStudentAssignment)
        .order_by(PsychologistStudentAssignment.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    if filters:
        query = query.where(*filters)

    rows = (await db.execute(query)).scalars().all()
    items = [
        PsychologistAssignmentItem(
            id=row.id,
            psychologist_id=row.psychologist_id,
            student_id=row.student_id,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return PsychologistAssignmentListResponse(
        items=items, total=total, page=page, limit=limit
    )


async def delete_assignment(db: AsyncSession, assignment_id: uuid.UUID) -> None:
    assignment = await db.get(PsychologistStudentAssignment, assignment_id)
    if assignment is None:
        raise ValueError("Assignment not found")
    await db.delete(assignment)
    await db.commit()
