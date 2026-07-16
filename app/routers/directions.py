from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.direction import DirectionBase, DirectionDetail, DirectionTreeNode
from app.services import direction_service

router = APIRouter(tags=["directions"])


@router.get("", response_model=list[DirectionBase])
async def list_directions(db: AsyncSession = Depends(get_db)) -> list[DirectionBase]:
    directions = await direction_service.get_all_directions(db)
    return [DirectionBase.model_validate(d) for d in directions]


@router.get("/tree", response_model=list[DirectionTreeNode])
async def list_direction_tree(
    db: AsyncSession = Depends(get_db),
) -> list[DirectionTreeNode]:
    """Spheres (sections) with nested leaf professions — for known-profession picker."""
    return await direction_service.get_direction_tree(db)


@router.get("/{slug}", response_model=DirectionDetail)
async def get_direction(slug: str, db: AsyncSession = Depends(get_db)) -> DirectionDetail:
    detail = await direction_service.get_direction_details(slug, db)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Direction not found")
    return detail
