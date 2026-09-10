import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.assessment import Assessment
from app.models.profile import Profile
from app.models.user import User
from app.schemas.psychoemotional import (
    SubmitPsychoEmotionalRequest,
    SubmitPsychoEmotionalResponse,
)
from app.services.psychoemotional import run_service

router = APIRouter(tags=["psychoemotional"])


@router.post(
    "/{assessment_id}/psychoemotional",
    response_model=SubmitPsychoEmotionalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_psychoemotional(
    assessment_id: uuid.UUID,
    data: SubmitPsychoEmotionalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubmitPsychoEmotionalResponse:
    """Сохранить одно прохождение психоэмоционального теста (append-only —
    повторное прохождение = новая строка). Результат пользователю не
    возвращается (§5.6)."""
    row = (
        await db.execute(
            select(Assessment.id, Profile.user_id)
            .join(Profile, Assessment.profile_id == Profile.id)
            .where(Assessment.id == assessment_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found"
        )
    if row.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    run = await run_service.create_run(
        assessment_id, data, user_id=current_user.id, db=db
    )
    return SubmitPsychoEmotionalResponse(
        run_id=run.id, tech_invalid=run.tech_invalid
    )
