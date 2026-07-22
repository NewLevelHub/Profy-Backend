import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.assessment import Assessment
from app.models.profile import Profile
from app.models.user import User
from app.schemas.subject_readiness import (
    SubjectQuestionOut,
    SubjectReadinessResult,
    SubmitSubjectAnswersRequest,
)
from app.services import subject_readiness_service

router = APIRouter(tags=["subject-readiness"])


async def _require_assessment_access(
    assessment_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> None:
    row = await db.execute(
        select(Assessment, Profile.user_id)
        .join(Profile, Assessment.profile_id == Profile.id)
        .where(Assessment.id == assessment_id)
    )
    row_data = row.one_or_none()
    if row_data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    _, owner_user_id = row_data
    if owner_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.get("/{assessment_id}/questions", response_model=list[SubjectQuestionOut])
async def get_subject_readiness_questions(
    assessment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SubjectQuestionOut]:
    await _require_assessment_access(assessment_id, current_user, db)
    return await subject_readiness_service.get_or_create_questions(assessment_id, db)


@router.post("/{assessment_id}/answers", response_model=SubjectReadinessResult)
async def submit_subject_readiness_answers(
    assessment_id: uuid.UUID,
    data: SubmitSubjectAnswersRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubjectReadinessResult:
    await _require_assessment_access(assessment_id, current_user, db)
    return await subject_readiness_service.submit_answers(assessment_id, data.answers, db)


@router.get("/{assessment_id}/result", response_model=SubjectReadinessResult)
async def get_subject_readiness_result(
    assessment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubjectReadinessResult:
    await _require_assessment_access(assessment_id, current_user, db)
    return await subject_readiness_service.get_result(assessment_id, db)
