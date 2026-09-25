"""Psychologist router — assigned students, their reports, notes, and report
review (PRO-327 / PRO-330 / PRO-337).

Mounted at `/api/v1/psychologist`. Psychologists never share admin routes;
access is gated with `require_role(UserRole.psychologist)`, and student
access (list/detail/report/notes) is further gated to students the admin has
assigned to that psychologist (PsychologistStudentAssignment, PRO-325/326).
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.extended_block_assignment import ExtendedBlock
from app.models.user import User, UserRole
from app.schemas.extended_block import AssignExtendedBlockRequest, ExtendedBlockAssignmentResponse
from app.schemas.psych_ai_analysis import PsychAiAnalysisOutput
from app.schemas.psychologist import (
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
from app.services import extended_block_service, psychologist_service
from app.services.psychologist_service import (
    ResultAlreadyPublishedError,
    ResultPatchInvalidError,
)

router = APIRouter(tags=["psychologist"])

_require_psychologist = require_role(UserRole.psychologist)
# The report endpoint alone also admits admin (PRO-338 Ф0.3) — every other
# route in this router stays psychologist-only, unchanged.
_require_psychologist_or_admin = require_role(UserRole.psychologist, UserRole.admin)

_RESULT_PATH = "/students/{student_id}/results/{assessment_id}"


@router.get("/reviews", response_model=list[PsychologistReviewQueueItem])
async def list_reviews(
    current_user: User = Depends(_require_psychologist),
    db: AsyncSession = Depends(get_db),
) -> list[PsychologistReviewQueueItem]:
    return await psychologist_service.list_pending_reviews(db, current_user.id)


@router.get(_RESULT_PATH, response_model=PsychologistResultDetailResponse)
async def get_result_for_review(
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
    current_user: User = Depends(_require_psychologist),
    db: AsyncSession = Depends(get_db),
) -> PsychologistResultDetailResponse:
    try:
        return await psychologist_service.get_result_for_review(
            db,
            psychologist_id=current_user.id,
            student_id=student_id,
            assessment_id=assessment_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch(_RESULT_PATH, response_model=PsychologistResultDetailResponse)
async def update_result_content(
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
    body: PsychologistResultPatch,
    current_user: User = Depends(_require_psychologist),
    db: AsyncSession = Depends(get_db),
) -> PsychologistResultDetailResponse:
    try:
        return await psychologist_service.update_result_content(
            db,
            psychologist_id=current_user.id,
            student_id=student_id,
            assessment_id=assessment_id,
            patch=body,
        )
    except ResultAlreadyPublishedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ResultPatchInvalidError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(f"{_RESULT_PATH}/publish", response_model=PsychologistResultDetailResponse)
async def publish_result(
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
    current_user: User = Depends(_require_psychologist),
    db: AsyncSession = Depends(get_db),
) -> PsychologistResultDetailResponse:
    try:
        return await psychologist_service.publish_result(
            db,
            psychologist_id=current_user.id,
            student_id=student_id,
            assessment_id=assessment_id,
        )
    except ResultAlreadyPublishedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/students",
    response_model=list[PsychologistStudentListItem | PsychologistAvailableStudentItem],
)
async def list_students(
    scope: Literal["mine", "available"] = Query(
        "mine",
        description=(
            "mine — students this psychologist already claimed; "
            "available — not yet claimed by them (PRO-337 / PRO-422). "
            "Prefer GET /students/available for the dedicated available shape."
        ),
    ),
    current_user: User = Depends(_require_psychologist),
    db: AsyncSession = Depends(get_db),
) -> list[PsychologistStudentListItem] | list[PsychologistAvailableStudentItem]:
    if scope == "available":
        return await psychologist_service.list_available_students(db, current_user.id)
    return await psychologist_service.list_assigned_students(db, current_user.id)


@router.get("/students/available", response_model=list[PsychologistAvailableStudentItem])
async def list_available_students(
    current_user: User = Depends(_require_psychologist),
    db: AsyncSession = Depends(get_db),
) -> list[PsychologistAvailableStudentItem]:
    """Pool of students this psychologist can claim — no admin in the flow."""
    return await psychologist_service.list_available_students(db, current_user.id)


@router.post(
    "/students/{student_id}/claim",
    response_model=PsychologistStudentListItem,
    status_code=status.HTTP_201_CREATED,
)
async def claim_student(
    student_id: uuid.UUID,
    current_user: User = Depends(_require_psychologist),
    db: AsyncSession = Depends(get_db),
) -> PsychologistStudentListItem:
    try:
        return await psychologist_service.claim_student(
            db, psychologist_id=current_user.id, student_id=student_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


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


@router.get(
    "/students/{student_id}/assessments/{assessment_id}/report",
    response_model=PsychologistReportResponse,
)
async def get_student_assessment_report(
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
    current_user: User = Depends(_require_psychologist_or_admin),
    db: AsyncSession = Depends(get_db),
) -> PsychologistReportResponse:
    try:
        return await psychologist_service.get_assigned_student_report(
            db,
            psychologist_id=current_user.id,
            student_id=student_id,
            assessment_id=assessment_id,
            viewer_role=current_user.role,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/students/{student_id}/assessments/{assessment_id}/test-results",
    response_model=PsychologistTestResultsResponse,
)
async def get_student_assessment_test_results(
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
    current_user: User = Depends(_require_psychologist_or_admin),
    db: AsyncSession = Depends(get_db),
) -> PsychologistTestResultsResponse:
    """Pure test-results surface: the 7 instruments alone, no narrative
    report content mixed in (contrast with `report`, above, which bundles
    `new_tests` together with the full student-shape RIASEC/BigFive
    report)."""
    try:
        return await psychologist_service.get_assigned_student_test_results(
            db,
            psychologist_id=current_user.id,
            student_id=student_id,
            assessment_id=assessment_id,
            viewer_role=current_user.role,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/students/{student_id}/assessments/{assessment_id}/report/ai-analysis/regenerate",
    response_model=PsychAiAnalysisOutput | None,
)
async def regenerate_report_ai_analysis(
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
    current_user: User = Depends(_require_psychologist_or_admin),
    db: AsyncSession = Depends(get_db),
) -> PsychAiAnalysisOutput | None:
    """Explicit "Обновить анализ" action — e.g. after finishing an extended
    block (Belbin/АСТУР) so the AI analysis reflects it, since the report's
    own GET only auto-generates once and caches. `None` (not an error) if
    generation is unavailable/fails — same "AI analysis may be absent"
    contract as the report endpoint's own `ai_analysis` field."""
    try:
        return await psychologist_service.regenerate_psych_ai_analysis(
            db,
            psychologist_id=current_user.id,
            student_id=student_id,
            assessment_id=assessment_id,
            viewer_role=current_user.role,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/students/{student_id}/assessments/{assessment_id}/extended-blocks",
    response_model=ExtendedBlockAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_extended_block(
    student_id: uuid.UUID,
    assessment_id: uuid.UUID,
    body: AssignExtendedBlockRequest,
    current_user: User = Depends(_require_psychologist_or_admin),
    db: AsyncSession = Depends(get_db),
) -> ExtendedBlockAssignmentResponse:
    """Post-Ф4.1 follow-up — «Назначить Belbin/АСТУР» replaces the raw
    hand-delivered link (Ф2.6/Ф3.6). Idempotent: re-assigning an
    already-assigned block just returns the existing assignment."""
    try:
        row = await psychologist_service.assign_extended_block(
            db,
            psychologist_id=current_user.id,
            student_id=student_id,
            assessment_id=assessment_id,
            block=ExtendedBlock(body.block),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    # Re-assigning an already-completed block is idempotent (returns the
    # existing row) — compute `completed` for real rather than hardcoding
    # False, so that case still reports accurately.
    assignments = await extended_block_service.list_assignments(assessment_id, db)
    completed = next((a["completed"] for a in assignments if a["block"] == row.block.value), False)
    return ExtendedBlockAssignmentResponse(
        block=row.block.value, assigned_at=row.assigned_at, completed=completed
    )


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
