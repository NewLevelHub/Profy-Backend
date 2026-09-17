"""Psychologist access to assigned students, their reports, and notes
(PRO-327 / PRO-330, assignments PRO-325/326).

Student list/detail/report are assignment-gated (PsychologistStudentAssignment).
Notes use soft cutoff: create requires an active assignment; list/update/delete
of notes the psychologist already owns do not — missing ownership/assignment
→ not-found (404), never 403.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.assessment import Assessment
from app.models.extended_block_assignment import ExtendedBlock, ExtendedBlockAssignment
from app.models.profile import Profile
from app.models.psychologist_assignment import PsychologistStudentAssignment
from app.models.psychologist_note import PsychologistNote
from app.models.user import User, UserRole
from app.schemas.admin import AdminUserDetailResponse
from app.schemas.psych_ai_analysis import PsychAiAnalysisOutput
from app.schemas.psychologist import (
    PsychologistAssessmentSummary,
    PsychologistNoteCreate,
    PsychologistNoteItem,
    PsychologistNoteUpdate,
    PsychologistReportResponse,
    PsychologistStudentDetailResponse,
    PsychologistStudentListItem,
)
from app.schemas.result_v2 import ResultResponseV2
from app.services import (
    admin_service,
    extended_block_service,
    new_tests_report_service,
    psych_ai_analysis_service,
    report_service,
)
from app.services.psych_ai_analysis_context import build_context, has_any_data

logger = logging.getLogger(__name__)


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


async def _require_student_assessment(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
) -> Assessment:
    """An assigned student and a real assessment_id aren't enough on their
    own — this closes the gap where a psychologist assigned to student A
    passes student B's assessment_id (or any other) in the URL and would
    otherwise see someone else's report."""
    result = await db.execute(
        select(Assessment)
        .join(Profile, Assessment.profile_id == Profile.id)
        .where(Assessment.id == assessment_id, Profile.user_id == student_id)
    )
    assessment = result.scalar_one_or_none()
    if assessment is None:
        raise ValueError("Assessment not found")
    return assessment


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


async def get_student_report(
    db: AsyncSession,
    *,
    psychologist_id: uuid.UUID,
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
    viewer: User,
) -> ResultResponseV2:
    """The student's full /result v2 report. `viewer` is the psychologist, so
    report_service.psych_sections_for → True and the validity / psychoemotional
    sections are attached (a student never sees these on their own
    /result)."""
    await _require_assigned_student(
        db, psychologist_id=psychologist_id, student_id=student_id
    )

    owns = await db.execute(
        select(Assessment.id)
        .join(Profile, Assessment.profile_id == Profile.id)
        .where(Assessment.id == assessment_id, Profile.user_id == student_id)
    )
    if owns.scalar_one_or_none() is None:
        raise ValueError("Assessment not found")

    return await report_service.build_report(assessment_id, db, viewer=viewer)


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


async def get_assigned_student_report(
    db: AsyncSession,
    *,
    psychologist_id: uuid.UUID,
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
    viewer_role: UserRole,
) -> PsychologistReportResponse:
    """PRO-338 Ф0.3/Ф4.1 — the specialist-only report surface (never the
    student-facing /result): the existing student-shape report — now
    including PRO-282's `validity`/`psychoemotional` sections, see
    `report_service.get_report_with_analysis`'s own Ф4.1 note — plus the 6
    new-tests sections (professional_types/team_role/temperament/
    intelligence/aspiration_level/empathy_confidence), the latter isolated
    per-section by new_tests_report_service so one malformed test never
    blanks the others or fails the whole request.

    `viewer_role` is always psychologist/admin here (the router's own
    `require_role` guarantees it before this is ever called) — passed
    through rather than hardcoded so `report_service.psych_sections_for`
    stays the single place that decides visibility, per its own module
    comment.

    Raises ValueError (→ 404 in the router) for: no assignment, an
    assessment_id that isn't this student's own, or no report generated yet
    for that assessment — the same "missing → 404, not 403" idiom as
    get_assigned_student_detail/_require_own_note above."""
    await _require_assigned_student(
        db, psychologist_id=psychologist_id, student_id=student_id
    )
    await _require_student_assessment(
        db, student_id=student_id, assessment_id=assessment_id
    )
    result = await report_service.get_report_with_analysis(assessment_id, db, viewer_role=viewer_role)
    if result is None:
        raise ValueError("Report not found")
    report, analysis = result
    new_tests = await new_tests_report_service.build_new_tests_sections(
        analysis, assessment_id=assessment_id, db=db
    )
    ai_analysis = await _get_or_generate_psych_ai_analysis(
        analysis, report=report, new_tests=new_tests, student_id=student_id, db=db
    )
    return PsychologistReportResponse(report=report, new_tests=new_tests, ai_analysis=ai_analysis)


async def _student_profile_name(student_id: uuid.UUID, db: AsyncSession) -> str:
    name = (
        await db.execute(select(Profile.name).where(Profile.user_id == student_id))
    ).scalar_one_or_none()
    return name or "Ученик"


async def _get_or_generate_psych_ai_analysis(
    analysis, *, report, new_tests, student_id: uuid.UUID, db: AsyncSession, force: bool = False
) -> PsychAiAnalysisOutput | None:
    """Lazily generates + caches the AI analysis on first view (product
    decision: auto-generate rather than requiring an explicit action first)
    — `analysis.psych_ai_analysis` is the cache, `force=True` (the
    regenerate endpoint) bypasses it and overwrites. Returns `None` without
    ever raising: an unavailable AI analysis must never break the rest of
    the report, same isolation principle as new_tests_report_service's
    per-section try/except."""
    if not force and analysis.psych_ai_analysis:
        try:
            return PsychAiAnalysisOutput.model_validate(analysis.psych_ai_analysis)
        except Exception:
            logger.exception(
                "Failed to parse cached psych_ai_analysis for assessment %s", analysis.assessment_id
            )
            # Fall through and regenerate — a malformed cached blob (e.g.
            # from an older schema version) shouldn't wedge this forever.

    try:
        student_name = await _student_profile_name(student_id, db)
        context = build_context(report, new_tests, student_name=student_name)
        if not has_any_data(context):
            return None
        output, is_ai_generated = await psych_ai_analysis_service.generate_psych_ai_analysis(context)
        if not is_ai_generated or output is None:
            return None
        analysis.psych_ai_analysis = output.model_dump(mode="json")
        await db.commit()
        return output
    except Exception:
        logger.exception(
            "Failed to generate psych_ai_analysis for assessment %s", analysis.assessment_id
        )
        return None


async def regenerate_psych_ai_analysis(
    db: AsyncSession,
    *,
    psychologist_id: uuid.UUID,
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
    viewer_role: UserRole,
) -> PsychAiAnalysisOutput | None:
    """Explicit "Обновить анализ" action — bypasses the cache even if one
    already exists (e.g. the psychologist just finished an extended block
    like Belbin/АСТУР and wants the analysis to reflect it)."""
    await _require_assigned_student(db, psychologist_id=psychologist_id, student_id=student_id)
    await _require_student_assessment(db, student_id=student_id, assessment_id=assessment_id)
    result = await report_service.get_report_with_analysis(assessment_id, db, viewer_role=viewer_role)
    if result is None:
        raise ValueError("Report not found")
    report, analysis = result
    new_tests = await new_tests_report_service.build_new_tests_sections(
        analysis, assessment_id=assessment_id, db=db
    )
    return await _get_or_generate_psych_ai_analysis(
        analysis, report=report, new_tests=new_tests, student_id=student_id, db=db, force=True
    )


async def assign_extended_block(
    db: AsyncSession,
    *,
    psychologist_id: uuid.UUID,
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
    block: ExtendedBlock,
) -> ExtendedBlockAssignment:
    """Post-Ф4.1 follow-up — replaces the raw hand-delivered Belbin/АСТУР
    link (Ф2.6/Ф3.6's original UX) with a real assignment the student's own
    UI can discover (GET .../extended-blocks). Same ownership checks as
    get_assigned_student_report; idempotent (see extended_block_service's
    own docstring — re-assigning is a no-op, not an error)."""
    await _require_assigned_student(
        db, psychologist_id=psychologist_id, student_id=student_id
    )
    await _require_student_assessment(
        db, student_id=student_id, assessment_id=assessment_id
    )
    return await extended_block_service.assign_block(
        assessment_id, block, psychologist_id=psychologist_id, db=db
    )
