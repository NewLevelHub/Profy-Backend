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
    FinishPsychoEmotionalRequest,
    FinishPsychoEmotionalResponse,
    StartPsychoEmotionalRequest,
    StartPsychoEmotionalResponse,
)
from app.services.psychoemotional import run_service

router = APIRouter(tags=["psychoemotional"])


async def _require_owned_assessment(
    assessment_id: uuid.UUID, current_user: User, db: AsyncSession
) -> None:
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


@router.post(
    "/{assessment_id}/psychoemotional/start",
    response_model=StartPsychoEmotionalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_psychoemotional(
    assessment_id: uuid.UUID,
    data: StartPsychoEmotionalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StartPsychoEmotionalResponse:
    """check-in + circle1 — перед основной батареей тестов (§B4 п.1-2).
    Результат пользователю не возвращается (§5.6)."""
    await _require_owned_assessment(assessment_id, current_user, db)
    run = await run_service.start_run(
        assessment_id, data, user_id=current_user.id, db=db
    )
    return StartPsychoEmotionalResponse(run_id=run.id)


@router.post(
    "/{assessment_id}/psychoemotional/{run_id}/finish",
    response_model=FinishPsychoEmotionalResponse,
)
async def finish_psychoemotional(
    assessment_id: uuid.UUID,
    run_id: uuid.UUID,
    data: FinishPsychoEmotionalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FinishPsychoEmotionalResponse:
    """circle2 — в конце всего прохождения."""
    await _require_owned_assessment(assessment_id, current_user, db)
    run = await run_service.finish_run(
        assessment_id, run_id, data, user_id=current_user.id, db=db
    )
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found or already finished",
        )
    return FinishPsychoEmotionalResponse(run_id=run.id, tech_invalid=run.tech_invalid)
