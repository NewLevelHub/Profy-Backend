import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_student_user
from app.models.assessment import Assessment
from app.models.profile import Profile
from app.models.user import User
from app.schemas.direction_inquiry import (
    DirectionQuestionsResponse,
    DirectionVerdictRequest,
    DirectionVerdictResponse,
)
from app.services import direction_inquiry_service

router = APIRouter(tags=["direction-inquiry"])


async def _require_assessment_access(
    assessment_id: uuid.UUID, current_user: User, db: AsyncSession
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


@router.get(
    "/{assessment_id}/directions/{slug}/questions",
    response_model=DirectionQuestionsResponse,
)
async def get_direction_questions(
    assessment_id: uuid.UUID,
    slug: str,
    current_user: User = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_db),
) -> DirectionQuestionsResponse:
    await _require_assessment_access(assessment_id, current_user, db)
    return await direction_inquiry_service.generate_questions(assessment_id, slug, db)


@router.post(
    "/{assessment_id}/directions/{slug}/verdict",
    response_model=DirectionVerdictResponse,
)
async def get_direction_verdict(
    assessment_id: uuid.UUID,
    slug: str,
    data: DirectionVerdictRequest,
    current_user: User = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_db),
) -> DirectionVerdictResponse:
    await _require_assessment_access(assessment_id, current_user, db)
    return await direction_inquiry_service.build_verdict(assessment_id, slug, data.answers, db)
