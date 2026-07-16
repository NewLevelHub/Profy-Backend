import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.routers.akinator import _require_owned_assessment, _turn_response
from app.schemas.simulation import (
    SimulationDetailResponse,
    SimulationSubmitRequest,
    SimulationSubmitResponse,
)
from app.services import akinator_session_service, simulation_service

router = APIRouter(tags=["simulation"])


@router.get(
    "/{assessment_id}/simulation/{leaf_slug}",
    response_model=SimulationDetailResponse,
)
async def get_simulation(
    assessment_id: uuid.UUID,
    leaf_slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SimulationDetailResponse:
    await _require_owned_assessment(assessment_id, current_user, db)

    sim = await simulation_service.get_simulation(leaf_slug, db)
    if sim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Симуляция для этой профессии не найдена",
        )

    return SimulationDetailResponse(
        leaf_slug=sim.leaf_slug,
        steps=sim.steps,
    )


@router.post(
    "/{assessment_id}/simulation/{leaf_slug}/submit",
    response_model=SimulationSubmitResponse,
)
async def submit_simulation(
    assessment_id: uuid.UUID,
    leaf_slug: str,
    data: SimulationSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SimulationSubmitResponse:
    age_group = await _require_owned_assessment(assessment_id, current_user, db)

    try:
        turn = await akinator_session_service.submit_simulation_outcome(
            assessment_id,
            leaf_slug,
            data.accepted,
            data.answers,
            age_group,
            db,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    akinator_turn = None
    if turn is not None:
        akinator_turn = await _turn_response(turn, age_group, db)

    return SimulationSubmitResponse(
        status="recorded",
        akinator_turn=akinator_turn,
    )
