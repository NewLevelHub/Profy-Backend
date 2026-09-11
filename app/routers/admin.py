import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_admin_user
from app.models.assessment import AssessmentGoal, AssessmentStatus
from app.models.motivation import MotivationCategory
from app.services.admin_lock import AdminNothingToClearError, AdminOverrideValidationError
from app.services.admin_listing import AdminSortFieldError, SortOrder
from app.models.user import User, UserRole
from app.schemas.admin import (
    AdminAssessmentDetailResponse,
    AdminFeedbackListResponse,
    AdminFeedbackStatsResponse,
    AdminUserCreate,
    AdminUserDetailResponse,
    AdminUserListResponse,
    AdminUserStatsResponse,
    PsychologistAssignmentCreate,
    PsychologistAssignmentItem,
    PsychologistAssignmentListResponse,
)
from app.schemas.admin_university import (
    AdminUniversityCountry,
    AdminUniversityListResponse,
    AdminUniversityDetail,
    AdminUniversityUpdateRequest,
    AdminProgramDetail,
    AdminProgramUpdateRequest,
)
from app.models.profile import AgeGroup
from app.models.question import QuestionInstrument
from app.schemas.admin_content import (
    AdminDirectionDetail,
    AdminDirectionListResponse,
    AdminDirectionUpdateRequest,
    AdminMotivationPairDetail,
    AdminMotivationPairListResponse,
    AdminMotivationPairUpdateRequest,
    AdminMotivationStatementDetail,
    AdminMotivationStatementListResponse,
    AdminMotivationStatementUpdateRequest,
    AdminQuestionDetail,
    AdminQuestionListResponse,
    AdminQuestionPairDetail,
    AdminQuestionPairListResponse,
    AdminQuestionPairUpdateRequest,
    AdminQuestionUpdateRequest,
)
from app.services import (
    admin_content_service,
    admin_export_service,
    admin_psychologist_service,
    admin_service,
    admin_university_service,
    university_service,
)

router = APIRouter(tags=["admin"])

# Every list endpoint takes the same two parameters; the set of values `sort`
# accepts is per-endpoint (services/admin_*_service.py: *_SORT_FIELDS) and an
# unknown one is a 422, not a silently ignored request.
_SORT_QUERY = Query(default=None, description="Field to sort by; see 422 body for the allowed set")
_ORDER_QUERY = Query(default="asc")



@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    age_group: AgeGroup | None = Query(default=None),
    status: AssessmentStatus | None = Query(default=None),
    goal: AssessmentGoal | None = Query(default=None),
    # Defaults to student: this list predates the role system, and every
    # row used to be a student by construction. Pass role=admin/psychologist
    # explicitly to see staff accounts (created via POST /users below).
    role: UserRole = Query(default=UserRole.student),
    inactive_days: int | None = Query(
        default=None, ge=1, description="Only users not seen for at least this many days"
    ),
    sort: str | None = _SORT_QUERY,
    order: SortOrder = _ORDER_QUERY,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.list_users(
        db,
        page=page,
        limit=limit,
        search=search,
        age_group=age_group,
        status=status,
        goal=goal,
        role=role,
        inactive_days=inactive_days,
        sort=sort,
        order=order,
    )


@router.post("/users", response_model=AdminUserDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: AdminUserCreate,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await admin_service.create_user(db, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    detail = await admin_service.get_user_detail(db, user.id)
    return detail


@router.get(
    "/psychologist-assignments",
    response_model=PsychologistAssignmentListResponse,
)
async def list_psychologist_assignments(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    psychologist_id: uuid.UUID | None = Query(default=None),
    student_id: uuid.UUID | None = Query(default=None),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_psychologist_service.list_assignments(
        db,
        page=page,
        limit=limit,
        psychologist_id=psychologist_id,
        student_id=student_id,
    )


@router.post(
    "/psychologist-assignments",
    response_model=PsychologistAssignmentItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_psychologist_assignment(
    body: PsychologistAssignmentCreate,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_psychologist_service.create_assignment(db, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/psychologist-assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_psychologist_assignment(
    assignment_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await admin_psychologist_service.delete_assignment(db, assignment_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users/stats", response_model=AdminUserStatsResponse)
async def get_user_stats(
    inactive_days: int = Query(
        default=admin_service.DEFAULT_INACTIVE_DAYS,
        ge=1,
        description="How long without being seen counts as abandoning a diagnostic",
    ),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.get_user_stats(db, inactive_days=inactive_days)


@router.get("/users/export")
async def export_users(
    search: str | None = Query(default=None),
    age_group: AgeGroup | None = Query(default=None),
    status: AssessmentStatus | None = Query(default=None),
    goal: AssessmentGoal | None = Query(default=None),
    role: UserRole = Query(default=UserRole.student),
    inactive_days: int | None = Query(default=None, ge=1),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        items = await admin_service.export_users(
            db,
            search=search,
            age_group=age_group,
            status=status,
            goal=goal,
            role=role,
            inactive_days=inactive_days,
        )
    except admin_service.ExportTooLargeError as e:
        # `status` (the query param above) shadows the fastapi `status`
        # module in this function's scope — use the `http_status` alias.
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    csv_text = admin_export_service.users_to_csv(items)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users_export.csv"},
    )


@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)
async def get_user_detail(
    user_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    detail = await admin_service.get_user_detail(db, user_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return detail


@router.get("/assessments/{assessment_id}", response_model=AdminAssessmentDetailResponse)
async def get_assessment_detail(
    assessment_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    detail = await admin_service.get_assessment_detail(db, assessment_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    return detail


@router.get("/assessments/{assessment_id}/export")
async def export_assessment(
    assessment_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    detail = await admin_service.get_assessment_detail(db, assessment_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    zip_bytes = admin_export_service.assessment_detail_to_zip(detail)
    filename = admin_export_service.assessment_export_filename(detail)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        # filename* (RFC 5987) carries the UTF-8 name; plain filename stays as
        # a fallback for clients that ignore it. Names here are Russian.
        headers={
            "Content-Disposition": (
                f"attachment; filename=assessment_{assessment_id}.zip; "
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )


@router.get("/feedback", response_model=AdminFeedbackListResponse)
async def list_feedback(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Substring of the free-text comment"),
    score_min: int | None = Query(default=None, ge=1, le=5),
    score_max: int | None = Query(default=None, ge=1, le=5),
    age_group: AgeGroup | None = Query(default=None),
    section: str | None = Query(default=None, description="One entry of helpful_sections"),
    has_comment: bool | None = Query(default=None),
    sort: str | None = _SORT_QUERY,
    order: SortOrder = _ORDER_QUERY,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.list_feedback(
        db,
        page=page,
        limit=limit,
        search=search,
        score_min=score_min,
        score_max=score_max,
        age_group=age_group,
        section=section,
        has_comment=has_comment,
        sort=sort,
        order=order,
    )


@router.get("/feedback/stats", response_model=AdminFeedbackStatsResponse)
async def get_feedback_stats(
    search: str | None = Query(default=None),
    score_min: int | None = Query(default=None, ge=1, le=5),
    score_max: int | None = Query(default=None, ge=1, le=5),
    age_group: AgeGroup | None = Query(default=None),
    section: str | None = Query(default=None),
    has_comment: bool | None = Query(default=None),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Same filters as GET /admin/feedback, so the summary describes exactly
    the rows the table is showing rather than always the whole table."""
    return await admin_service.get_feedback_stats(
        db,
        search=search,
        score_min=score_min,
        score_max=score_max,
        age_group=age_group,
        section=section,
        has_comment=has_comment,
    )


@router.get("/universities", response_model=AdminUniversityListResponse)
async def list_universities(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(
        default=None, description="Matches name, short name, city or any alias"
    ),
    country: str | None = Query(default=None),
    has_ranking: bool | None = Query(default=None),
    has_programs: bool | None = Query(
        default=None, description="false = universities no student can ever be matched to"
    ),
    sort: str | None = _SORT_QUERY,
    order: SortOrder = _ORDER_QUERY,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_university_service.list_universities(
        db,
        page=page,
        limit=limit,
        search=search,
        country=country,
        has_ranking=has_ranking,
        has_programs=has_programs,
        sort=sort,
        order=order,
    )


@router.get("/universities/countries", response_model=list[AdminUniversityCountry])
async def list_university_countries(
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Options for the country filter. A page of 20 rows cannot supply them,
    and downloading the whole catalog to count them client-side is what this
    replaces."""
    return await admin_university_service.list_countries(db)


@router.get("/universities/{university_id}", response_model=AdminUniversityDetail)
async def get_university_detail(
    university_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    detail = await admin_university_service.get_university_detail(db, university_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="University not found")
    return detail


@router.patch("/universities/{university_id}", response_model=AdminUniversityDetail)
async def update_university(
    university_id: uuid.UUID,
    data: AdminUniversityUpdateRequest,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_university_service.update_university(db, university_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/programs/{program_id}", response_model=AdminProgramDetail)
async def get_program_detail(
    program_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await university_service.get_program_by_id(db, program_id)
    except HTTPException:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found")


@router.patch("/programs/{program_id}", response_model=AdminProgramDetail)
async def update_program(
    program_id: uuid.UUID,
    data: AdminProgramUpdateRequest,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_university_service.update_program(db, program_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/questions", response_model=AdminQuestionListResponse)
async def list_questions(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    instrument: QuestionInstrument | None = Query(default=None),
    age_tier: AgeGroup | None = Query(default=None),
    search: str | None = Query(default=None),
    has_overrides: bool | None = Query(
        default=None, description="Only rows edited by hand (or only untouched ones)"
    ),
    sort: str | None = _SORT_QUERY,
    order: SortOrder = _ORDER_QUERY,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_content_service.list_questions(
        db,
        instrument=instrument,
        age_tier=age_tier,
        search=search,
        has_overrides_filter=has_overrides,
        sort=sort,
        order=order,
        page=page,
        limit=limit,
    )


@router.get("/questions/{question_id}", response_model=AdminQuestionDetail)
async def get_question_detail(
    question_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    detail = await admin_content_service.get_question_detail(db, question_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return detail


@router.patch("/questions/{question_id}", response_model=AdminQuestionDetail)
async def update_question(
    question_id: uuid.UUID,
    data: AdminQuestionUpdateRequest,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_content_service.update_question(db, question_id, data)
    except AdminOverrideValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/question-pairs", response_model=AdminQuestionPairListResponse)
async def list_question_pairs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    instrument: QuestionInstrument | None = Query(default=None),
    age_tier: AgeGroup | None = Query(default=None),
    search: str | None = Query(
        default=None, description="Matches the frame and the option texts a student sees"
    ),
    has_overrides: bool | None = Query(default=None),
    sort: str | None = _SORT_QUERY,
    order: SortOrder = _ORDER_QUERY,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_content_service.list_question_pairs(
        db,
        instrument=instrument,
        age_tier=age_tier,
        search=search,
        has_overrides_filter=has_overrides,
        sort=sort,
        order=order,
        page=page,
        limit=limit,
    )


@router.get("/question-pairs/{pair_id}", response_model=AdminQuestionPairDetail)
async def get_question_pair_detail(
    pair_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    detail = await admin_content_service.get_question_pair_detail(db, pair_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question pair not found")
    return detail


@router.patch("/question-pairs/{pair_id}", response_model=AdminQuestionPairDetail)
async def update_question_pair(
    pair_id: uuid.UUID,
    data: AdminQuestionPairUpdateRequest,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_content_service.update_question_pair(db, pair_id, data)
    except AdminOverrideValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/motivation-statements", response_model=AdminMotivationStatementListResponse)
async def list_motivation_statements(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Matches text or text_junior"),
    triplet_index: int | None = Query(
        default=None, description="Show one whole triplet — its three statements"
    ),
    category: MotivationCategory | None = Query(default=None),
    has_overrides: bool | None = Query(default=None),
    sort: str | None = _SORT_QUERY,
    order: SortOrder = _ORDER_QUERY,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_content_service.list_motivation_statements(
        db,
        search=search,
        triplet_index=triplet_index,
        category=category,
        has_overrides_filter=has_overrides,
        sort=sort,
        order=order,
        page=page,
        limit=limit,
    )


@router.get(
    "/motivation-statements/{statement_id}", response_model=AdminMotivationStatementDetail
)
async def get_motivation_statement_detail(
    statement_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    detail = await admin_content_service.get_motivation_statement_detail(db, statement_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Motivation statement not found"
        )
    return detail


@router.patch(
    "/motivation-statements/{statement_id}", response_model=AdminMotivationStatementDetail
)
async def update_motivation_statement(
    statement_id: uuid.UUID,
    data: AdminMotivationStatementUpdateRequest,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_content_service.update_motivation_statement(db, statement_id, data)
    except AdminOverrideValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/motivation-pairs", response_model=AdminMotivationPairListResponse)
async def list_motivation_pairs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Matches text_a or text_b"),
    category: MotivationCategory | None = Query(default=None),
    has_overrides: bool | None = Query(default=None),
    sort: str | None = _SORT_QUERY,
    order: SortOrder = _ORDER_QUERY,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_content_service.list_motivation_pairs(
        db,
        search=search,
        category=category,
        has_overrides_filter=has_overrides,
        sort=sort,
        order=order,
        page=page,
        limit=limit,
    )


@router.get("/motivation-pairs/{pair_id}", response_model=AdminMotivationPairDetail)
async def get_motivation_pair_detail(
    pair_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    detail = await admin_content_service.get_motivation_pair_detail(db, pair_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Motivation pair not found"
        )
    return detail


@router.patch("/motivation-pairs/{pair_id}", response_model=AdminMotivationPairDetail)
async def update_motivation_pair(
    pair_id: uuid.UUID,
    data: AdminMotivationPairUpdateRequest,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_content_service.update_motivation_pair(db, pair_id, data)
    except AdminOverrideValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/directions", response_model=AdminDirectionListResponse)
async def list_directions(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Matches name or slug"),
    catalog_filled: bool | None = Query(
        default=None, description="false = rows with at least one empty catalog field"
    ),
    has_overrides: bool | None = Query(default=None),
    sort: str | None = _SORT_QUERY,
    order: SortOrder = _ORDER_QUERY,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_content_service.list_directions(
        db,
        search=search,
        catalog_filled=catalog_filled,
        has_overrides_filter=has_overrides,
        sort=sort,
        order=order,
        page=page,
        limit=limit,
    )


@router.get("/directions/{direction_id}", response_model=AdminDirectionDetail)
async def get_direction_detail(
    direction_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    detail = await admin_content_service.get_direction_detail(db, direction_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Direction not found")
    return detail


@router.patch("/directions/{direction_id}", response_model=AdminDirectionDetail)
async def update_direction(
    direction_id: uuid.UUID,
    data: AdminDirectionUpdateRequest,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_content_service.update_direction(db, direction_id, data)
    except AdminOverrideValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# --- Undoing admin edits ----------------------------------------------------
#
# A PATCH on question-bank content records an override that a resync composes
# back over the bank on every deploy, so without these an accidental edit was
# permanent and only reachable by hand in the database
# (docs/admin-backend-requests-pro-242.md §4). Clearing an override restores
# the bank value captured when the field was first edited.


@router.delete("/questions/{row_id}/overrides", response_model=AdminQuestionDetail)
async def clear_question_overrides(
    row_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Drop every override on the row, putting it fully back under the bank."""
    try:
        return await admin_content_service.clear_question_overrides(db, row_id)
    except AdminNothingToClearError as e:
        # The row is fine; the caller's view of it was stale. 409, not 404,
        # so the client can refresh the row instead of leaving the page.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/questions/{row_id}/overrides/{field}", response_model=AdminQuestionDetail)
async def clear_question_override_field(
    row_id: uuid.UUID,
    field: str,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_content_service.clear_question_overrides(db, row_id, field)
    except AdminNothingToClearError as e:
        # The row is fine; the caller's view of it was stale. 409, not 404,
        # so the client can refresh the row instead of leaving the page.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/question-pairs/{row_id}/overrides", response_model=AdminQuestionPairDetail)
async def clear_question_pair_overrides(
    row_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Drop every override on the row, putting it fully back under the bank."""
    try:
        return await admin_content_service.clear_question_pair_overrides(db, row_id)
    except AdminNothingToClearError as e:
        # The row is fine; the caller's view of it was stale. 409, not 404,
        # so the client can refresh the row instead of leaving the page.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/question-pairs/{row_id}/overrides/{field}", response_model=AdminQuestionPairDetail)
async def clear_question_pair_override_field(
    row_id: uuid.UUID,
    field: str,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_content_service.clear_question_pair_overrides(db, row_id, field)
    except AdminNothingToClearError as e:
        # The row is fine; the caller's view of it was stale. 409, not 404,
        # so the client can refresh the row instead of leaving the page.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/motivation-statements/{row_id}/overrides", response_model=AdminMotivationStatementDetail)
async def clear_motivation_statement_overrides(
    row_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Drop every override on the row, putting it fully back under the bank."""
    try:
        return await admin_content_service.clear_motivation_statement_overrides(db, row_id)
    except AdminNothingToClearError as e:
        # The row is fine; the caller's view of it was stale. 409, not 404,
        # so the client can refresh the row instead of leaving the page.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/motivation-statements/{row_id}/overrides/{field}", response_model=AdminMotivationStatementDetail)
async def clear_motivation_statement_override_field(
    row_id: uuid.UUID,
    field: str,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_content_service.clear_motivation_statement_overrides(db, row_id, field)
    except AdminNothingToClearError as e:
        # The row is fine; the caller's view of it was stale. 409, not 404,
        # so the client can refresh the row instead of leaving the page.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/motivation-pairs/{row_id}/overrides", response_model=AdminMotivationPairDetail)
async def clear_motivation_pair_overrides(
    row_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Drop every override on the row, putting it fully back under the bank."""
    try:
        return await admin_content_service.clear_motivation_pair_overrides(db, row_id)
    except AdminNothingToClearError as e:
        # The row is fine; the caller's view of it was stale. 409, not 404,
        # so the client can refresh the row instead of leaving the page.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/motivation-pairs/{row_id}/overrides/{field}", response_model=AdminMotivationPairDetail)
async def clear_motivation_pair_override_field(
    row_id: uuid.UUID,
    field: str,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_content_service.clear_motivation_pair_overrides(db, row_id, field)
    except AdminNothingToClearError as e:
        # The row is fine; the caller's view of it was stale. 409, not 404,
        # so the client can refresh the row instead of leaving the page.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/directions/{row_id}/overrides", response_model=AdminDirectionDetail)
async def clear_direction_overrides(
    row_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Drop every override on the row, putting it fully back under the bank."""
    try:
        return await admin_content_service.clear_direction_overrides(db, row_id)
    except AdminNothingToClearError as e:
        # The row is fine; the caller's view of it was stale. 409, not 404,
        # so the client can refresh the row instead of leaving the page.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/directions/{row_id}/overrides/{field}", response_model=AdminDirectionDetail)
async def clear_direction_override_field(
    row_id: uuid.UUID,
    field: str,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_content_service.clear_direction_overrides(db, row_id, field)
    except AdminNothingToClearError as e:
        # The row is fine; the caller's view of it was stale. 409, not 404,
        # so the client can refresh the row instead of leaving the page.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# `University`/`Program` use admin_locked_fields instead of value-carrying
# overrides: the lock stores only the field's name, so unlocking cannot undo
# the edit — it returns the field to the next seed run's control.


@router.delete("/universities/{university_id}/locks", response_model=AdminUniversityDetail)
async def unlock_university_fields(
    university_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_university_service.unlock_university_fields(db, university_id)
    except AdminNothingToClearError as e:
        # The row is fine; the caller's view of it was stale. 409, not 404,
        # so the client can refresh the row instead of leaving the page.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/universities/{university_id}/locks/{field}", response_model=AdminUniversityDetail)
async def unlock_university_field(
    university_id: uuid.UUID,
    field: str,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_university_service.unlock_university_fields(db, university_id, field)
    except AdminNothingToClearError as e:
        # The row is fine; the caller's view of it was stale. 409, not 404,
        # so the client can refresh the row instead of leaving the page.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/programs/{program_id}/locks", response_model=AdminProgramDetail)
async def unlock_program_fields(
    program_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_university_service.unlock_program_fields(db, program_id)
    except AdminNothingToClearError as e:
        # The row is fine; the caller's view of it was stale. 409, not 404,
        # so the client can refresh the row instead of leaving the page.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/programs/{program_id}/locks/{field}", response_model=AdminProgramDetail)
async def unlock_program_field(
    program_id: uuid.UUID,
    field: str,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_university_service.unlock_program_fields(db, program_id, field)
    except AdminNothingToClearError as e:
        # The row is fine; the caller's view of it was stale. 409, not 404,
        # so the client can refresh the row instead of leaving the page.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
