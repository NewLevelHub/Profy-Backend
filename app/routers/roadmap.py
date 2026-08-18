import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.assessment import Assessment
from app.models.profile import Profile
from app.models.program import Program
from app.models.user import User
from app.schemas.roadmap import (
    DirectionRoadmapResponse,
    GenerateDirectionRoadmapRequest,
    RoadmapResponse,
)
from app.services import roadmap_builder

router = APIRouter(tags=["roadmap"])


class GenerateRoadmapRequest(BaseModel):
    assessment_id: uuid.UUID
    program_id: uuid.UUID | None = None


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


@router.post("/generate", response_model=RoadmapResponse)
async def generate_roadmap(
    data: GenerateRoadmapRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoadmapResponse:
    await _require_assessment_access(data.assessment_id, current_user, db)
    return await roadmap_builder.generate_roadmap(data.assessment_id, data.program_id, db)


@router.post("/direction", response_model=DirectionRoadmapResponse)
async def generate_direction_roadmap(
    data: GenerateDirectionRoadmapRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DirectionRoadmapResponse:
    """Confirm a direction after the AI inquiry and build the in-direction plan."""
    await _require_assessment_access(data.assessment_id, current_user, db)
    if data.program_id is not None:
        program = (
            await db.execute(select(Program).where(Program.id == data.program_id))
        ).scalar_one_or_none()
        if program is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Program not found",
            )
        if data.direction_slug not in (program.profession_slugs or []):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Program does not belong to this direction",
            )
    return await roadmap_builder.generate_direction_roadmap(
        data.assessment_id, data.direction_slug, db, data.program_id
    )


@router.get("/{assessment_id}/directions/{slug}", response_model=DirectionRoadmapResponse)
async def get_direction_roadmap(
    assessment_id: uuid.UUID,
    slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DirectionRoadmapResponse:
    await _require_assessment_access(assessment_id, current_user, db)
    result = await roadmap_builder.get_direction_roadmap(assessment_id, slug, db)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roadmap not found")
    return result


@router.get("/{assessment_id}", response_model=RoadmapResponse)
async def get_roadmap(
    assessment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoadmapResponse:
    await _require_assessment_access(assessment_id, current_user, db)
    result = await roadmap_builder.get_roadmap(assessment_id, db)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roadmap not found")
    return result
