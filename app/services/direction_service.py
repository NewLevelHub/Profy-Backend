from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.direction import Direction
from app.schemas.direction import DirectionBase, DirectionDetail


async def get_all_directions(db: AsyncSession) -> list[Direction]:
    result = await db.execute(select(Direction).order_by(Direction.name))
    return list(result.scalars().all())


async def get_direction_by_slug(slug: str, db: AsyncSession) -> Direction | None:
    result = await db.execute(select(Direction).where(Direction.slug == slug))
    return result.scalar_one_or_none()


async def get_direction_details(slug: str, db: AsyncSession) -> DirectionDetail | None:
    direction = await get_direction_by_slug(slug, db)
    if direction is None:
        return None
    return DirectionDetail.model_validate(direction)


def best_matching_slug(profession_slugs: list[str], careers: list[dict]) -> str | None:
    """Which of a program's `profession_slugs` best matches this student.

    "Best" = highest in their `careers` top list (lowest index). Falls back to
    the first slug in `profession_slugs` if none of them made the student's
    top list at all — a program still needs *some* direction to build a plan
    against. Returns None only if `profession_slugs` is itself empty.

    Pure function, no I/O — shared by `goal_overlay_service` (scenario C
    alignment) and `roadmap_builder` (university direction-roadmap by
    program), previously duplicated between the two."""
    best_index: int | None = None
    best_slug: str | None = None
    for slug in profession_slugs:
        idx = next((i for i, c in enumerate(careers) if c.get("slug") == slug), None)
        if idx is not None and (best_index is None or idx < best_index):
            best_index = idx
            best_slug = slug
    if best_slug is not None:
        return best_slug
    return profession_slugs[0] if profession_slugs else None


__all__ = [
    "get_all_directions",
    "get_direction_by_slug",
    "get_direction_details",
    "best_matching_slug",
    "DirectionBase",
]
