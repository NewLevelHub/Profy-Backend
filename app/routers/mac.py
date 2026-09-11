"""МАК — пользовательская часть (PRO-315/316). Mounted at `/api/v1/mac`.
Не по буквальной форме тикета (`GET /mac/session`) — `POST /mac/session`
с телом `{assessment_id}`, т.к. эндпоинт get-or-create'ит сессию, а не
только читает её; остальные пути — как в тикете."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.assessment import Assessment
from app.models.profile import Profile
from app.models.user import User
from app.schemas.mac import (
    MacCardOut,
    MacSessionResponse,
    MacSpreadResponse,
    SubmitMacResponseRequest,
    SubmitMacResponseResponse,
)
from app.services import mac_service

router = APIRouter(tags=["mac"])


class _CreateSessionRequest(BaseModel):
    assessment_id: uuid.UUID


class _DrawRequest(BaseModel):
    exercise_id: uuid.UUID


async def _require_assessment_owner(
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    if row.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.post("/session", response_model=MacSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_or_get_session(
    body: _CreateSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MacSessionResponse:
    await _require_assessment_owner(body.assessment_id, current_user, db)
    session = await mac_service.get_or_create_session(
        db, assessment_id=body.assessment_id, user_id=current_user.id
    )
    return await mac_service.build_session_response(db, session)


@router.post("/session/{session_id}/draw", response_model=MacCardOut)
async def draw_card(
    session_id: uuid.UUID,
    body: _DrawRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MacCardOut:
    try:
        card = await mac_service.draw_blind_card(
            db, session_id=session_id, exercise_id=body.exercise_id, user_id=current_user.id
        )
    except mac_service.MacAccessError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return mac_service.card_to_out(card)


@router.get("/exercise/{exercise_id}/spread", response_model=MacSpreadResponse)
async def get_spread(
    exercise_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MacSpreadResponse:
    try:
        cards, pick_count = await mac_service.get_spread(db, exercise_id=exercise_id)
    except mac_service.MacAccessError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return MacSpreadResponse(
        cards=[mac_service.card_to_out(c) for c in cards], pick_count=pick_count
    )


@router.post("/response", response_model=SubmitMacResponseResponse, status_code=status.HTTP_201_CREATED)
async def submit_response(
    body: SubmitMacResponseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubmitMacResponseResponse:
    try:
        response, completed = await mac_service.submit_response(db, body, user_id=current_user.id)
    except mac_service.MacAccessError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return SubmitMacResponseResponse(response_id=response.id, session_completed=completed)
