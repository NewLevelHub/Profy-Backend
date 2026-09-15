"""Psychologist access to assigned students, notes and report review
(PRO-327 / PRO-330 / PRO-337).

Student list/detail are assignment-gated. Notes use soft cutoff: create
requires an active assignment; list/update/delete of notes the psychologist
already owns do not — missing ownership → not-found (404), never 403.
Report review (docs/psychologist-review-gate-plan.md §3) requires an active
assignment for every call.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.analysis_result import AnalysisResult, ReviewStatus
from app.models.analysis_result_review_edit import AnalysisResultReviewEdit
from app.models.assessment import Assessment
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
from app.schemas.psychologist_result import (
    PsychologistResultDetailResponse,
    PsychologistResultPatch,
    PsychologistReviewQueueItem,
)
from app.services import admin_service, assessment_shared, email_service

logger = logging.getLogger(__name__)


class ResultAlreadyPublishedError(Exception):
    """Edit or publish of a result that is already published → 409."""


class ResultPatchInvalidError(Exception):
    """Well-formed patch that doesn't fit the stored result → 422."""


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
                review_status=a.review_status,
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


# --- Report review (PRO-337) -------------------------------------------------


# Hard cap on both review queues. Neither is paginated in the UI, and a
# backlog that large means the queue is not being worked at all — cutting it
# off keeps one runaway response from carrying every pending report.
REVIEW_QUEUE_LIMIT = 200


def review_queue_select(limit: int = REVIEW_QUEUE_LIMIT) -> Select:
    """Results waiting for review, oldest first — shared by the psychologist
    queue and the admin "no psychologist assigned" queue, which differ only
    in how they filter on `PsychologistStudentAssignment` (joined live, never
    snapshotted, so a later assignment pulls existing results in)."""
    student = aliased(User)
    return (
        select(
            AnalysisResult.assessment_id,
            AnalysisResult.created_at.label("generated_at"),
            AnalysisResult.reviewed_at,
            Assessment.goal,
            student.id.label("student_id"),
            student.email.label("student_email"),
            Profile.name.label("student_name"),
            Profile.age_group,
        )
        .join(Assessment, Assessment.id == AnalysisResult.assessment_id)
        .join(Profile, Profile.id == Assessment.profile_id)
        .join(student, student.id == Profile.user_id)
        .where(AnalysisResult.review_status == ReviewStatus.pending_review)
        .order_by(AnalysisResult.created_at.asc())
        .limit(limit)
    )


def to_review_queue_items(rows: Any) -> list[PsychologistReviewQueueItem]:
    return [
        PsychologistReviewQueueItem(
            assessment_id=row.assessment_id,
            student_id=row.student_id,
            student_name=row.student_name,
            student_email=row.student_email,
            age_group=row.age_group.value if row.age_group is not None else None,
            goal=row.goal.value,
            generated_at=row.generated_at,
            reviewed_at=row.reviewed_at,
        )
        for row in rows
    ]


async def list_pending_reviews(
    db: AsyncSession, psychologist_id: uuid.UUID
) -> list[PsychologistReviewQueueItem]:
    query = review_queue_select().join(
        PsychologistStudentAssignment,
        PsychologistStudentAssignment.student_id == Profile.user_id,
    ).where(PsychologistStudentAssignment.psychologist_id == psychologist_id)
    return to_review_queue_items((await db.execute(query)).all())


async def _require_result_for_student(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
    for_update: bool = False,
) -> AnalysisResult:
    query = (
        select(AnalysisResult)
        .join(Assessment, Assessment.id == AnalysisResult.assessment_id)
        .join(Profile, Profile.id == Assessment.profile_id)
        .where(
            AnalysisResult.assessment_id == assessment_id,
            Profile.user_id == student_id,
        )
    )
    if for_update:
        # Serializes concurrent PATCH/publish on one result; populate_existing
        # so a row already in the session is re-read under the lock.
        query = query.with_for_update(of=AnalysisResult).execution_options(
            populate_existing=True
        )
    analysis = (await db.execute(query)).scalar_one_or_none()
    if analysis is None:
        raise ValueError("Result not found")
    return analysis


async def get_result_for_review(
    db: AsyncSession,
    *,
    psychologist_id: uuid.UUID,
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
) -> PsychologistResultDetailResponse:
    await _require_assigned_student(
        db, psychologist_id=psychologist_id, student_id=student_id
    )
    analysis = await _require_result_for_student(
        db, student_id=student_id, assessment_id=assessment_id
    )
    return PsychologistResultDetailResponse.model_validate(analysis)


async def update_result_content(
    db: AsyncSession,
    *,
    psychologist_id: uuid.UUID,
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
    patch: PsychologistResultPatch,
) -> PsychologistResultDetailResponse:
    await _require_assigned_student(
        db, psychologist_id=psychologist_id, student_id=student_id
    )
    analysis = await _require_result_for_student(
        db, student_id=student_id, assessment_id=assessment_id, for_update=True
    )
    if analysis.review_status != ReviewStatus.pending_review:
        raise ResultAlreadyPublishedError("Result is already published")

    values = patch.model_dump(exclude_unset=True, mode="json")
    # strengths/weaknesses are category codes the student report is rebuilt
    # from (careers "why", interest map) — free text there would break it.
    allowed_codes = set(analysis.profile)
    for field in ("strengths", "weaknesses"):
        unknown = set(values.get(field, [])) - allowed_codes
        if unknown:
            raise ResultPatchInvalidError(
                f"{field}: unknown codes {sorted(unknown)}, allowed {sorted(allowed_codes)}"
            )

    changed: dict[str, dict[str, Any]] = {}
    for field, new_value in values.items():
        old_value = getattr(analysis, field)
        if old_value != new_value:
            changed[field] = {"old": old_value, "new": new_value}
            setattr(analysis, field, new_value)

    analysis.reviewed_by = psychologist_id
    analysis.reviewed_at = datetime.now(timezone.utc)
    if changed:
        db.add(
            AnalysisResultReviewEdit(
                analysis_result_id=analysis.id,
                editor_id=psychologist_id,
                changed_fields=changed,
            )
        )
    await db.commit()
    await db.refresh(analysis)
    detail = PsychologistResultDetailResponse.model_validate(analysis)
    await _drop_report_cache(assessment_id)
    return detail


async def publish_result(
    db: AsyncSession,
    *,
    psychologist_id: uuid.UUID,
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
) -> PsychologistResultDetailResponse:
    await _require_assigned_student(
        db, psychologist_id=psychologist_id, student_id=student_id
    )
    analysis = await _require_result_for_student(
        db, student_id=student_id, assessment_id=assessment_id, for_update=True
    )
    return await _publish(db, analysis, publisher_id=psychologist_id)


async def publish_result_as_admin(
    db: AsyncSession, *, admin_id: uuid.UUID, assessment_id: uuid.UUID
) -> PsychologistResultDetailResponse:
    """Admin fallback for results whose student has no psychologist
    (docs/psychologist-review-gate-plan.md §4) — not assignment-gated."""
    query = (
        select(AnalysisResult)
        .where(AnalysisResult.assessment_id == assessment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    analysis = (await db.execute(query)).scalar_one_or_none()
    if analysis is None:
        raise ValueError("Result not found")
    return await _publish(db, analysis, publisher_id=admin_id)


async def _publish(
    db: AsyncSession, analysis: AnalysisResult, *, publisher_id: uuid.UUID
) -> PsychologistResultDetailResponse:
    if analysis.review_status == ReviewStatus.published:
        raise ResultAlreadyPublishedError("Result is already published")
    now = datetime.now(timezone.utc)
    analysis.review_status = ReviewStatus.published
    analysis.published_by = publisher_id
    analysis.published_at = now
    # Published without edits — publishing still counts as a review.
    if analysis.reviewed_by is None:
        analysis.reviewed_by = publisher_id
        analysis.reviewed_at = now
    await db.commit()
    await db.refresh(analysis)
    detail = PsychologistResultDetailResponse.model_validate(analysis)
    await _drop_report_cache(analysis.assessment_id)
    await _notify_result_published(db, analysis.assessment_id)
    return detail


async def _drop_report_cache(assessment_id: uuid.UUID) -> None:
    """Defensive — unpublished reports are never cached in the first place
    (report_service._cache_if_published); the next student GET after
    publishing warms the cache again."""
    await assessment_shared.safe_redis_delete(
        assessment_shared.get_redis(), assessment_shared.report_cache_key(assessment_id)
    )


async def notify_review_pending(
    db: AsyncSession, *, student_id: uuid.UUID, student_name: str | None
) -> None:
    """Email every psychologist assigned to the student that a new report
    waits for review. Best-effort: never raises into report generation."""
    try:
        result = await db.execute(
            select(User.email)
            .join(
                PsychologistStudentAssignment,
                PsychologistStudentAssignment.psychologist_id == User.id,
            )
            .where(PsychologistStudentAssignment.student_id == student_id)
        )
        emails = list(result.scalars().all())
    except Exception:
        logger.exception("review-pending recipients lookup failed for student=%s", student_id)
        return
    for email in emails:
        try:
            await email_service.send_review_pending_email(email, student_name or "без имени")
        except Exception:
            logger.exception("review-pending email to %s failed", email)


async def _notify_result_published(db: AsyncSession, assessment_id: uuid.UUID) -> None:
    """Email the student that their report is published. Best-effort."""
    try:
        row = (
            await db.execute(
                select(User.email, Profile.name)
                .join(Profile, Profile.user_id == User.id)
                .join(Assessment, Assessment.profile_id == Profile.id)
                .where(Assessment.id == assessment_id)
            )
        ).one_or_none()
        if row is not None:
            await email_service.send_result_published_email(row.email, row.name or "Привет")
    except Exception:
        logger.exception("result-published notification failed for assessment=%s", assessment_id)
