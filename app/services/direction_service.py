from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import pick_locale, pick_locale_list
from app.models.direction import Direction
from app.schemas.direction import DirectionBase, DirectionDetail


async def get_all_directions(db: AsyncSession) -> list[Direction]:
    # Order by the ru title — a stable, always-populated sort key regardless
    # of UI locale (matches the pre-JSONB ordering, since `ru` was always the
    # canonical/complete set).
    result = await db.execute(select(Direction).order_by(Direction.name["ru"].astext))
    return list(result.scalars().all())


async def get_direction_by_slug(slug: str, db: AsyncSession) -> Direction | None:
    result = await db.execute(select(Direction).where(Direction.slug == slug))
    return result.scalar_one_or_none()


def to_base_schema(direction: Direction, locale: str | None = None) -> DirectionBase:
    return DirectionBase(
        id=direction.id,
        name=pick_locale(direction.name, locale),
        slug=direction.slug,
        holland_code=direction.holland_code,
    )


def to_detail_schema(direction: Direction, locale: str | None = None) -> DirectionDetail:
    return DirectionDetail(
        id=direction.id,
        name=pick_locale(direction.name, locale),
        slug=direction.slug,
        holland_code=direction.holland_code,
        description=pick_locale(direction.description, locale),
        professions=pick_locale_list(direction.professions, locale),
        skills_needed=pick_locale_list(direction.skills_needed, locale),
        subjects_to_develop=pick_locale_list(direction.subjects_to_develop, locale),
        first_steps=pick_locale_list(direction.first_steps, locale),
    )


async def get_direction_details(slug: str, db: AsyncSession) -> DirectionDetail | None:
    direction = await get_direction_by_slug(slug, db)
    if direction is None:
        return None
    return to_detail_schema(direction)


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
