from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.direction import Direction


async def get_direction_by_slug(slug: str, db: AsyncSession) -> Direction | None:
    result = await db.execute(select(Direction).where(Direction.slug == slug))
    return result.scalar_one_or_none()


__all__ = ["get_direction_by_slug"]
