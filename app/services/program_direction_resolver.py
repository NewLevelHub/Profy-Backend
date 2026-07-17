"""Map akinator profession slugs to university program direction_slug values.

After the test, `Assessment.selected_direction_slug` is a profession leaf slug
(e.g. `programmer`). Seeded university programs are tagged with the parent
section slug (e.g. `akinator-it-data`) so recommendations match the test result.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.direction import Direction


async def program_direction_slugs_for(selected_slug: str, db: AsyncSession) -> list[str]:
    """Return slug(s) to use when looking up university programs for a test result."""
    slugs: list[str] = [selected_slug]

    direction = (
        await db.execute(select(Direction).where(Direction.slug == selected_slug))
    ).scalar_one_or_none()
    if direction is not None and direction.parent_id is not None:
        parent = await db.get(Direction, direction.parent_id)
        if parent is not None:
            slugs.append(parent.slug)

    return list(dict.fromkeys(slugs))
