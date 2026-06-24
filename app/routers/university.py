import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.university import ProgramBrief, ProgramDetail
from app.services.university_service import get_program_by_id, search_programs

router = APIRouter(tags=["universities"])


@router.get("/programs", response_model=list[ProgramBrief])
async def list_programs(
    direction: str = Query(..., description="Direction slug, e.g. it-development"),
    country: str | None = Query(None, description="ISO country code or name, e.g. us or Kazakhstan"),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[ProgramBrief]:
    return await search_programs(db, direction_slug=direction, country=country, limit=limit)


@router.get("/programs/{program_id}", response_model=ProgramDetail)
async def get_program(
    program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ProgramDetail:
    return await get_program_by_id(db, program_id)
