"""Psychologist access to assigned students (PRO-327 / Milestone 2).

Scope is assignment-gated: a psychologist only sees students linked via
`PsychologistStudentAssignment`. Missing assignment → not-found (404 at the
router), never 403 — same pattern as `_require_profile_id` /
`_require_assessment_access`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.profile import Profile
from app.models.psychologist_assignment import PsychologistStudentAssignment
from app.models.user import User
from app.schemas.admin import AdminUserDetailResponse
from app.schemas.psychologist import (
    PsychologistAssessmentSummary,
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
