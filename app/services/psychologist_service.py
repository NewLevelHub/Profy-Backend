"""Psychologist access to assigned students, their reports, notes and report
review (PRO-327 / PRO-330 / PRO-337, assignments PRO-325/326).

Student list/detail/report are assignment-gated (PsychologistStudentAssignment).
Notes use soft cutoff: create requires an active assignment; list/update/delete
of notes the psychologist already owns do not — missing ownership/assignment
→ not-found (404), never 403.
Report review (docs/psychologist-review-gate-plan.md §3) requires an active
assignment for every call.
"""

from __future__ import annotations


import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, case, delete, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.i18n.catalog import key as i18n_key
from app.i18n import DEFAULT_LOCALE
from app.models.analysis_result import AnalysisResult, ReviewStatus
from app.models.analysis_result_review_edit import AnalysisResultReviewEdit
from app.models.assessment import Assessment, AssessmentStatus
from app.models.extended_block_assignment import ExtendedBlock, ExtendedBlockAssignment
from app.models.profile import Profile
from app.models.psychologist_assignment import PsychologistStudentAssignment
from app.models.psychologist_note import PsychologistNote
from app.models.user import User, UserRole
from app.schemas.admin import AdminUserDetailResponse
from app.schemas.psych_ai_analysis import PsychAiAnalysisOutput
from app.schemas.psychologist import (
    PsychologistAssessmentSummary,
    PsychologistAvailableStudentItem,
    PsychologistNoteCreate,
    PsychologistNoteItem,
    PsychologistNoteUpdate,
    PsychologistReportResponse,
    PsychologistStudentDetailResponse,
    PsychologistStudentListItem,
    PsychologistTestResultsResponse,
)
from app.schemas.psychologist_result import (
    PsychologistResultDetailResponse,
    PsychologistResultPatch,
    PsychologistReviewQueueItem,
)
from app.services import (
    admin_service,
    assessment_shared,
    bigfive_content,
    email_service,
    extended_block_service,
    new_tests_report_service,
    psych_ai_analysis_service,
    report_service,
)
from app.services.psych_ai_analysis_context import build_context, has_any_data, fingerprint as context_fingerprint

logger = logging.getLogger(__name__)


# Notifications sit on request paths (report generation, publishing). Sending
# is best-effort, so the request waits for the whole step at most this long —
# per-recipient timeouts would still add up on a slow provider and could push
# POST /result/generate past nginx's own timeout.
_NOTIFY_BUDGET_SECONDS = 5


# Sends that outlive the budget keep running after the request moves on; the
# loop only holds weak references to tasks, so keep strong ones until done.
_background_sends: set[asyncio.Task] = set()


def _forget_send(task: asyncio.Task) -> None:
    _background_sends.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.error("notification send failed", exc_info=task.exception())


async def _send_within_budget(sends: list[Any]) -> None:
    if not sends:
        return
    tasks = [asyncio.ensure_future(send) for send in sends]
    for task in tasks:
        _background_sends.add(task)
        task.add_done_callback(_forget_send)
    # asyncio.wait, not wait_for(gather(...)): on timeout the request stops
    # waiting but nothing is cancelled. The email pool has two workers, so a
    # send queued behind a slow provider would otherwise be cancelled before
    # it ever started and that recipient silently never notified.
    _done, pending = await asyncio.wait(tasks, timeout=_NOTIFY_BUDGET_SECONDS)
    if pending:
        logger.warning(
            "notification budget of %ss exceeded — %d send(s) continue in the background",
            _NOTIFY_BUDGET_SECONDS,
            len(pending),
        )


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
        raise ValueError(i18n_key("api_errors", "student_not_found", locale="ru"))
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
        raise ValueError(i18n_key("api_errors", "assessment_not_found", locale="ru"))
    return assessment


async def _require_own_note(
    db: AsyncSession,
    *,
    psychologist_id: uuid.UUID,
    note_id: uuid.UUID,
) -> PsychologistNote:
    note = await db.get(PsychologistNote, note_id)
    if note is None or note.psychologist_id != psychologist_id:
        raise ValueError(i18n_key("api_errors", "note_not_found", locale="ru"))
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
            Profile.age,
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
            age=row.age,
            assigned_at=row.created_at,
        )
        for row in rows
    ]


async def list_available_students(
    db: AsyncSession, psychologist_id: uuid.UUID
) -> list[PsychologistAvailableStudentItem]:
    """Students the psychologist can claim — role=student and not yet
    assigned to this psychologist (PRO-337: selection without admin)."""
    already_mine = (
        select(PsychologistStudentAssignment.student_id)
        .where(PsychologistStudentAssignment.psychologist_id == psychologist_id)
    )
    pending = (
        select(AnalysisResult.id)
        .join(Assessment, Assessment.id == AnalysisResult.assessment_id)
        .join(Profile, Profile.id == Assessment.profile_id)
        .where(
            Profile.user_id == User.id,
            AnalysisResult.review_status == ReviewStatus.pending_review,
        )
        .exists()
    )
    completed = (
        select(Assessment.id)
        .join(Profile, Profile.id == Assessment.profile_id)
        .where(
            Profile.user_id == User.id,
            Assessment.status == AssessmentStatus.completed,
        )
        .exists()
    )
    query = (
        select(
            User.id,
            User.email,
            Profile.name,
            Profile.age,
            pending.label("has_pending"),
            completed.label("has_completed"),
        )
        .outerjoin(Profile, Profile.user_id == User.id)
        .where(User.role == UserRole.student, ~User.id.in_(already_mine))
        .order_by(User.created_at.desc())
    )
    rows = (await db.execute(query)).all()
    return [
        PsychologistAvailableStudentItem(
            id=row.id,
            email=row.email,
            profile_name=row.name,
            age=row.age,
            has_pending_review=bool(row.has_pending),
            has_completed_assessment=bool(row.has_completed),
        )
        for row in rows
    ]


async def claim_student(
    db: AsyncSession, *, psychologist_id: uuid.UUID, student_id: uuid.UUID
) -> PsychologistStudentListItem:
    """Psychologist self-assigns a student. Admin is not in this flow."""
    student = await db.get(User, student_id)
    if student is None or student.role != UserRole.student:
        raise ValueError(i18n_key("api_errors", "student_not_found", locale="ru"))

    existing = await db.execute(
        select(PsychologistStudentAssignment).where(
            PsychologistStudentAssignment.psychologist_id == psychologist_id,
            PsychologistStudentAssignment.student_id == student_id,
        )
    )
    assignment = existing.scalar_one_or_none()
    if assignment is None:
        assignment = PsychologistStudentAssignment(
            psychologist_id=psychologist_id,
            student_id=student_id,
        )
        db.add(assignment)
        await db.commit()
        await db.refresh(assignment)
    else:
        # Idempotent claim — already mine.
        pass

    profile = (
        await db.execute(select(Profile).where(Profile.user_id == student_id))
    ).scalar_one_or_none()
    return PsychologistStudentListItem(
        id=student.id,
        email=student.email,
        profile_name=profile.name if profile is not None else None,
        age=profile.age if profile is not None else None,
        assigned_at=assignment.created_at,
    )


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
        raise ValueError(i18n_key("api_errors", "student_not_found", locale="ru"))
    return _to_psychologist_detail(detail)


async def get_assigned_student_test_results(
    db: AsyncSession,
    *,
    psychologist_id: uuid.UUID,
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
    viewer_role: UserRole,
) -> PsychologistTestResultsResponse:
    """Pure test-results surface for one assessment: the same 7 instruments
    `get_assigned_student_report` bundles into `new_tests`/`report.
    psychoemotional`, flattened into one narrative-free payload — no
    summary/careers/strength_cards/personality_notes from the student-shape
    report. Same auth/lookup contract as `get_assigned_student_report`
    (ValueError → 404 in the router)."""
    await _require_assigned_student(
        db, psychologist_id=psychologist_id, student_id=student_id
    )
    await _require_student_assessment(
        db, student_id=student_id, assessment_id=assessment_id
    )
    result = await report_service.get_report_with_analysis(assessment_id, db, viewer_role=viewer_role)
    if result is None:
        raise ValueError(i18n_key("api_errors", "report_not_found", locale="ru"))
    report, analysis = result
    new_tests = await new_tests_report_service.build_new_tests_sections(
        analysis, assessment_id=assessment_id, db=db
    )
    return PsychologistTestResultsResponse(
        professional_types=new_tests.professional_types,
        team_role=new_tests.team_role,
        temperament=new_tests.temperament,
        intelligence=new_tests.intelligence,
        aspiration_level=new_tests.aspiration_level,
        empathy_confidence=new_tests.empathy_confidence,
        psychoemotional=report.psychoemotional,
    )


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
        raise ValueError(i18n_key("api_errors", "report_not_found", locale="ru"))
    report, analysis = result
    new_tests = await new_tests_report_service.build_new_tests_sections(
        analysis, assessment_id=assessment_id, db=db
    )
    ai_analysis = await _get_or_generate_psych_ai_analysis(
        analysis, report=report, new_tests=new_tests, student_id=student_id, db=db
    )
    return PsychologistReportResponse(report=report, new_tests=new_tests, ai_analysis=ai_analysis)


async def _student_profile_facts(student_id: uuid.UUID, db: AsyncSession) -> tuple[str, int | None, int | None]:
    fallback = i18n_key("report_copy", "student_fallback_name", locale="ru")
    row = (
        await db.execute(select(Profile.name, Profile.age, Profile.grade).where(Profile.user_id == student_id))
    ).one_or_none()
    if row is None:
        return fallback, None, None
    return row.name or fallback, row.age, row.grade


async def _get_or_generate_psych_ai_analysis(
    analysis, *, report, new_tests, student_id: uuid.UUID, db: AsyncSession, force: bool = False
) -> PsychAiAnalysisOutput | None:
    """Lazily generates + caches the AI analysis on first view (product
    decision: auto-generate rather than requiring an explicit action first)
    — `analysis.psych_ai_analysis` is the cache, `force=True` (the
    regenerate endpoint) bypasses it and overwrites. The cache is valid only
    for the inputs it was built from (`psych_ai_analysis_fingerprint`,
    PRO-427): a new completed АСТУР attempt, a new scoring version or a
    changed age regenerates it, and pre-fingerprint caches (which may still
    talk about СПН/fatigue) are always regenerated. Returns `None` without
    ever raising: an unavailable AI analysis must never break the rest of
    the report, same isolation principle as new_tests_report_service's
    per-section try/except."""
    try:
        student_name, student_age, student_grade = await _student_profile_facts(student_id, db)
        context = build_context(
            report, new_tests,
            student_name=student_name, student_age=student_age, student_grade=student_grade,
        )
        inputs_fingerprint = context_fingerprint(context)
    except Exception:
        logger.exception("Failed to build psych_ai_analysis context for assessment %s", analysis.assessment_id)
        return None

    cache_is_current = analysis.psych_ai_analysis_fingerprint == inputs_fingerprint
    if not force and analysis.psych_ai_analysis and cache_is_current:
        try:
            return PsychAiAnalysisOutput.model_validate(analysis.psych_ai_analysis)
        except Exception:
            logger.exception(
                "Failed to parse cached psych_ai_analysis for assessment %s", analysis.assessment_id
            )
            # Fall through and regenerate — a malformed cached blob (e.g.
            # from an older schema version) shouldn't wedge this forever.

    try:
        if not has_any_data(context):
            return None
        output, is_ai_generated = await psych_ai_analysis_service.generate_psych_ai_analysis(context)
        if not is_ai_generated or output is None:
            return None
        analysis.psych_ai_analysis = output.model_dump(mode="json")
        analysis.psych_ai_analysis_fingerprint = inputs_fingerprint
        await db.commit()
        return output
    except Exception:
        logger.exception(
            "Failed to generate psych_ai_analysis for assessment %s", analysis.assessment_id
        )
        return None


# --- Report review (PRO-337) -------------------------------------------------


# Hard cap on both review queues. Neither is paginated in the UI, and a
# backlog that large means the queue is not being worked at all — cutting it
# off keeps one runaway response from carrying every pending report.
REVIEW_QUEUE_LIMIT = 200


def _is_original_row() -> Any:
    """KZ-405 keeps one report row per locale; they share one review status,
    and the queue, the review page and publishing all work on a single one of
    them — "the row under review". That is the `ru` row when there is one
    (report_service._find_primary_analysis translates from it, and the
    psychologist cabinet is Russian), else the earliest.

    Not "the earliest" alone: `created_at` is `now()`, i.e. the *transaction*
    start, so locale rows written in one transaction tie, and an id
    tie-break would then pick a translation at random."""
    other = aliased(AnalysisResult)

    def _rank(row: Any) -> Any:
        return case((row.locale == DEFAULT_LOCALE, 0), else_=1)

    return ~(
        select(other.id)
        .where(
            other.assessment_id == AnalysisResult.assessment_id,
            tuple_(_rank(other), other.created_at, other.id)
            < tuple_(_rank(AnalysisResult), AnalysisResult.created_at, AnalysisResult.id),
        )
        .exists()
    )


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
            Profile.age,
        )
        .join(Assessment, Assessment.id == AnalysisResult.assessment_id)
        .join(Profile, Profile.id == Assessment.profile_id)
        .join(student, student.id == Profile.user_id)
        .where(AnalysisResult.review_status == ReviewStatus.pending_review, _is_original_row())
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
            age=row.age,
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
            _is_original_row(),
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
        raise ValueError(i18n_key("api_errors", "result_not_found", locale="ru"))
    return analysis


def _to_detail(analysis: AnalysisResult) -> PsychologistResultDetailResponse:
    """`personality_notes` is the one field the psychologist must not see
    straight from the row: the stored text is adult-phrased and the student
    reads a computed, age-appropriate phrase instead. Show (and let them
    edit) exactly what the student reads."""
    detail = PsychologistResultDetailResponse.model_validate(analysis)
    return detail.model_copy(
        update={"personality_notes": report_service.student_personality_notes(analysis)}
    )


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
    return _to_detail(analysis)


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
        raise ValueError(i18n_key("api_errors", "report_not_found", locale="ru"))
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
    # Serialize with report generation: a locale row generated in between
    # would be a translation of the pre-edit text (edit) or miss the
    # published status (publish).
    await report_service.lock_report_generation(assessment_id, db)
    analysis = await _require_result_for_student(
        db, student_id=student_id, assessment_id=assessment_id, for_update=True
    )
    if analysis.review_status != ReviewStatus.pending_review:
        raise ResultAlreadyPublishedError(i18n_key("api_errors", "result_is_already_published", locale="ru"))

    values = patch.model_dump(exclude_unset=True, mode="json")

    # "Твой характер" is stored apart from the rest: the student reads a
    # computed phrase, so a correction is kept as an override of that phrase,
    # trait by trait — untouched traits keep following the scores.
    notes_patch = values.pop("personality_notes", None)
    if notes_patch is not None:
        unknown_traits = set(notes_patch) - set(bigfive_content.personality_labels())
        if unknown_traits:
            raise ResultPatchInvalidError(
                i18n_key("api_errors", "unknown_personality_traits", locale="ru").format(traits=sorted(unknown_traits))
            )
        if any(not text.strip() for text in notes_patch.values()):
            raise ResultPatchInvalidError(i18n_key("api_errors", "empty_personality_note", locale="ru"))

    # strengths/weaknesses are category codes the student report is rebuilt
    # from (careers "why", interest map) — free text there would break it.
    allowed_codes = set(analysis.profile)
    for field in ("strengths", "weaknesses"):
        unknown = set(values.get(field, [])) - allowed_codes
        if unknown:
            raise ResultPatchInvalidError(
                i18n_key("api_errors", "unknown_result_codes", locale="ru").format(field=field, codes=sorted(unknown), allowed_codes=sorted(allowed_codes))
            )

    changed: dict[str, dict[str, Any]] = {}
    for field, new_value in values.items():
        old_value = getattr(analysis, field)
        if old_value != new_value:
            changed[field] = {"old": old_value, "new": new_value}
            setattr(analysis, field, new_value)

    if notes_patch is not None:
        default_notes = report_service.student_personality_notes(analysis, include_overrides=False)
        # Only genuine corrections are stored — a trait left at its computed
        # wording must keep following the scores, not freeze today's phrasing.
        # Merge, don't replace: omitting a trait means "leave as is" here too,
        # so a later one-trait correction can't silently drop earlier ones.
        # Typing the computed phrase back in removes the override for that trait.
        new_override = dict(analysis.personality_notes_override)
        for trait, text in notes_patch.items():
            if text.strip() == default_notes.get(trait, "").strip():
                new_override.pop(trait, None)
            else:
                new_override[trait] = text
        if new_override != dict(analysis.personality_notes_override):
            changed["personality_notes"] = {
                "old": report_service.student_personality_notes(analysis),
                "new": {**default_notes, **new_override},
            }
            analysis.personality_notes_override = new_override

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
        # Other-locale rows are translations of the text as it was *before*
        # this edit — publishing them would ship unreviewed content. Drop them;
        # the next request in that locale re-translates from the edited row
        # and inherits its review status (report_service.build_report).
        stale_rows = select(AnalysisResult.id).where(
            AnalysisResult.assessment_id == analysis.assessment_id,
            AnalysisResult.id != analysis.id,
        )
        # Keep the audit trail. A kk-first report edited before a ru
        # translation existed has its history on the kk row; once ru becomes
        # the row under review, deleting kk would cascade that history away,
        # and _carry_over_review_edits relies on it to keep rewritten
        # descriptions in every future translation.
        await db.execute(
            update(AnalysisResultReviewEdit)
            .where(AnalysisResultReviewEdit.analysis_result_id.in_(stale_rows))
            .values(analysis_result_id=analysis.id)
        )
        await db.execute(
            delete(AnalysisResult).where(
                AnalysisResult.assessment_id == analysis.assessment_id,
                AnalysisResult.id != analysis.id,
            )
        )
    await db.commit()
    await db.refresh(analysis)
    detail = _to_detail(analysis)
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
    # Serialize with report generation: a locale row generated in between
    # would be a translation of the pre-edit text (edit) or miss the
    # published status (publish).
    await report_service.lock_report_generation(assessment_id, db)
    analysis = await _require_result_for_student(
        db, student_id=student_id, assessment_id=assessment_id, for_update=True
    )
    return await _publish(db, analysis, publisher_id=psychologist_id)


async def _publish(
    db: AsyncSession, analysis: AnalysisResult, *, publisher_id: uuid.UUID
) -> PsychologistResultDetailResponse:
    if analysis.review_status == ReviewStatus.published:
        raise ResultAlreadyPublishedError(i18n_key("api_errors", "result_is_already_published", locale="ru"))
    now = datetime.now(timezone.utc)
    analysis.review_status = ReviewStatus.published
    analysis.published_by = publisher_id
    analysis.published_at = now
    # Published without edits — publishing still counts as a review.
    if analysis.reviewed_by is None:
        analysis.reviewed_by = publisher_id
        analysis.reviewed_at = now
    # Remaining translations (only ever made from the current, reviewed text —
    # an edit drops older ones) share the report's status: publish them too,
    # or a student on that locale would keep seeing "under review".
    await db.execute(
        update(AnalysisResult)
        .where(
            AnalysisResult.assessment_id == analysis.assessment_id,
            AnalysisResult.id != analysis.id,
        )
        .values(
            review_status=ReviewStatus.published,
            reviewed_by=analysis.reviewed_by,
            reviewed_at=analysis.reviewed_at,
            published_by=publisher_id,
            published_at=now,
        )
    )
    await db.commit()
    await db.refresh(analysis)
    detail = _to_detail(analysis)
    await _drop_report_cache(analysis.assessment_id)
    await _notify_result_published(db, analysis.assessment_id)
    return detail


async def _drop_report_cache(assessment_id: uuid.UUID) -> None:
    """Defensive — unpublished reports are never cached in the first place
    (report_service._cache_if_published); the next student GET after
    publishing warms the cache again."""
    await assessment_shared.safe_redis_delete(
        assessment_shared.get_redis(), *assessment_shared.report_cache_keys(assessment_id)
    )


async def notify_review_pending(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    student_name: str | None,
    assessment_id: uuid.UUID,
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
    review_url = email_service.frontend_url(
        f"/psychologist/students/{student_id}/results/{assessment_id}/review"
    )
    await _send_within_budget(
        [
            email_service.send_review_pending_email(
                email, student_name or i18n_key("report_copy", "unnamed_student", locale="ru"), review_url=review_url
            )
            for email in emails
        ]
    )


async def _notify_result_published(db: AsyncSession, assessment_id: uuid.UUID) -> None:
    """Email the student that their report is published. Best-effort."""
    try:
        row = (
            await db.execute(
                select(User.email, User.locale, Profile.name)
                .join(Profile, Profile.user_id == User.id)
                .join(Assessment, Assessment.profile_id == Profile.id)
                .where(Assessment.id == assessment_id)
            )
        ).one_or_none()
        if row is not None:
            results_url = email_service.frontend_url("/results")
            await _send_within_budget(
                [
                    email_service.send_result_published_email(
                        row.email,
                        row.name,
                        locale=row.locale,
                        results_url=results_url,
                    )
                ]
            )
    except Exception:
        logger.exception("result-published notification failed for assessment=%s", assessment_id)
