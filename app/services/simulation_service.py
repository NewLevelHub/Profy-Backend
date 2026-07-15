from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profession_simulation import ProfessionSimulation


async def get_simulation(leaf_slug: str, db: AsyncSession) -> ProfessionSimulation | None:
    result = await db.execute(
        select(ProfessionSimulation).where(ProfessionSimulation.leaf_slug == leaf_slug)
    )
    return result.scalar_one_or_none()
