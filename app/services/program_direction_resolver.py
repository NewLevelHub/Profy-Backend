"""Map akinator profession slugs to university program direction_slugs values.

After the test, `Assessment.selected_direction_slug` is a profession leaf slug
(e.g. `software-engineer`). Seeded university programs are tagged with one or
more akinator specialty/section slugs in `Program.direction_slugs` (JSONB list)
so recommendations match the test result.

Use `program_matches` (pure, sync) to check whether a single program's slugs
overlap with the allowed set — e.g. in gap-analysis validation.
Use `program_direction_slugs_for` (async, DB) to expand a selected slug to the
full set that should be accepted when querying.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.direction import Direction


def program_matches(program_direction_slugs: list[str], allowed_slugs: list[str]) -> bool:
    """Return True when the program covers at least one of the allowed slugs.

    Pure set-intersection helper — no DB access, safe to call from any context.

    Args:
        program_direction_slugs: the ``Program.direction_slugs`` list from the ORM object.
        allowed_slugs: the list returned by ``program_direction_slugs_for``.

    Returns:
        True if the intersection is non-empty, False otherwise.
    """
    return bool(set(program_direction_slugs) & set(allowed_slugs))


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
