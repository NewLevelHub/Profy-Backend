"""Admin CRUD for psychologist↔student assignments (PRO-326 / Milestone 2).

Role checks live here, not in the DB — `PsychologistStudentAssignment` only
enforces the unique (psychologist_id, student_id) pair. See
docs/user-roles-integration-plan.md Milestone 2.
"""

from __future__ import annotations


import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n.catalog import key as i18n_key
from app.models.profile import Profile
from app.models.psychologist_assignment import PsychologistStudentAssignment
from app.models.user import User, UserRole
from app.schemas.admin import (
    PsychologistAssignmentCreate,
    PsychologistAssignmentItem,
    PsychologistAssignmentListResponse,
)
from app.schemas.psychologist_result import PsychologistReviewQueueItem
from app.services import psychologist_service


async def create_assignment(
    db: AsyncSession, body: PsychologistAssignmentCreate
) -> PsychologistStudentAssignment:
    psychologist = await db.get(User, body.psychologist_id)
    if psychologist is None:
        raise ValueError(i18n_key("api_errors", "psychologist_not_found", locale="ru"))
    if psychologist.role != UserRole.psychologist:
        raise ValueError(i18n_key("api_errors", "invalid_psychologist_role", locale="ru"))

    student = await db.get(User, body.student_id)
    if student is None:
        raise ValueError(i18n_key("api_errors", "student_not_found", locale="ru"))
    if student.role != UserRole.student:
        raise ValueError(i18n_key("api_errors", "invalid_student_role", locale="ru"))

    existing = await db.execute(
        select(PsychologistStudentAssignment).where(
            PsychologistStudentAssignment.psychologist_id == body.psychologist_id,
            PsychologistStudentAssignment.student_id == body.student_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError(i18n_key("api_errors", "assignment_already_exists", locale="ru"))

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


async def list_unassigned_reviews(
    db: AsyncSession, *, limit: int = psychologist_service.REVIEW_QUEUE_LIMIT
) -> list[PsychologistReviewQueueItem]:
    """Results waiting for review whose student has no psychologist at all —
    without this queue they would never be published
    (docs/psychologist-review-gate-plan.md §4)."""
    has_assignment = (
        select(PsychologistStudentAssignment.id)
        .where(PsychologistStudentAssignment.student_id == Profile.user_id)
        .exists()
    )
    query = psychologist_service.review_queue_select(limit).where(~has_assignment)
    return psychologist_service.to_review_queue_items((await db.execute(query)).all())


async def delete_assignment(db: AsyncSession, assignment_id: uuid.UUID) -> None:
    assignment = await db.get(PsychologistStudentAssignment, assignment_id)
    if assignment is None:
        raise ValueError(i18n_key("api_errors", "assignment_not_found", locale="ru"))
    await db.delete(assignment)
    await db.commit()
