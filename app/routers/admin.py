import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_admin_user
from app.i18n import KNOWN_LOCALES
from app.models.assessment import AssessmentGoal, AssessmentStatus
from app.services.admin_lock import AdminOverrideValidationError
from app.models.user import User
from app.schemas.admin import (
    AdminAssessmentDetailResponse,
    AdminFeedbackListResponse,
    AdminFeedbackStatsResponse,
    AdminUserDetailResponse,
    AdminUserListResponse,
)
from app.schemas.admin_university import (
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
    admin_service,
    admin_university_service,
    university_service,
)

router = APIRouter(tags=["admin"])


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    age_group: AgeGroup | None = Query(default=None),
    status: AssessmentStatus | None = Query(default=None),
    goal: AssessmentGoal | None = Query(default=None),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.list_users(
        db, page=page, limit=limit, search=search, age_group=age_group, status=status, goal=goal
    )


@router.get("/users/export")
async def export_users(
    search: str | None = Query(default=None),
    age_group: AgeGroup | None = Query(default=None),
    status: AssessmentStatus | None = Query(default=None),
    goal: AssessmentGoal | None = Query(default=None),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        items = await admin_service.export_users(
            db, search=search, age_group=age_group, status=status, goal=goal
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
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=assessment_{assessment_id}.zip"},
    )


@router.get("/feedback", response_model=AdminFeedbackListResponse)
async def list_feedback(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.list_feedback(db, page=page, limit=limit)


@router.get("/feedback/stats", response_model=AdminFeedbackStatsResponse)
async def get_feedback_stats(
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.get_feedback_stats(db)


@router.get("/universities", response_model=AdminUniversityListResponse)
async def list_universities(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_university_service.list_universities(db, page=page, limit=limit, search=search)


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


# Admin content lists show one row per (logical unit, locale) since KZ-301, so
# every list endpoint below takes the same optional locale filter. Built from
# KNOWN_LOCALES rather than a literal so the accepted set can't drift from
# app/i18n (see the warning on KNOWN_LOCALES itself).
AdminLocaleFilter = Annotated[
    str | None,
    Query(
        pattern=f"^({'|'.join(KNOWN_LOCALES)})$",
        description="Show only rows of this locale. Omit to list every locale.",
    ),
]


@router.get("/questions", response_model=AdminQuestionListResponse)
async def list_questions(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    instrument: QuestionInstrument | None = Query(default=None),
    age_tier: AgeGroup | None = Query(default=None),
    search: str | None = Query(default=None),
    locale: AdminLocaleFilter = None,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_content_service.list_questions(
        db, instrument=instrument, age_tier=age_tier, search=search, locale=locale, page=page, limit=limit
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
    locale: AdminLocaleFilter = None,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_content_service.list_question_pairs(
        db, instrument=instrument, age_tier=age_tier, locale=locale, page=page, limit=limit
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
    locale: AdminLocaleFilter = None,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_content_service.list_motivation_statements(db, locale=locale, page=page, limit=limit)


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
    locale: AdminLocaleFilter = None,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_content_service.list_motivation_pairs(db, locale=locale, page=page, limit=limit)


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
    search: str | None = Query(default=None),
    locale: AdminLocaleFilter = None,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await admin_content_service.list_directions(db, search=search, locale=locale, page=page, limit=limit)


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
