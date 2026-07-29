from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.direction import Direction
from app.schemas.direction import DirectionBase, DirectionDetail, DirectionTreeNode


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


async def get_direction_tree(db: AsyncSession) -> list[DirectionTreeNode]:
    """Return Akinator sections with nested leaf professions, sorted by name.

    Feeds the "I already know my profession" picker (known-profession flow).
    Excludes junior/middle-only leaves (the 6 `explore-*` nodes, age_groups
    `["junior", "middle"]`, no "senior") — these are the Akinator engine's
    own internal fallback reveal buckets for junior sessions that don't
    differentiate within the real 57-specialty catalog, not real
    professions a user would ever type into "I already know what I want".
    They also have no matching row in `known_profession_quizzes` (seeded
    only for the 57 real specialties), so picking one here 404s on the
    next step — junior isn't a wired-up branch of the app yet either way.
    """
    result = await db.execute(select(Direction).order_by(Direction.name))
    all_dirs = list(result.scalars().all())

    sections = [d for d in all_dirs if not d.is_leaf and d.parent_id is None]
    leaves = [d for d in all_dirs if d.is_leaf and "senior" in (d.age_groups or [])]

    by_parent: dict = {}
    for leaf in leaves:
        by_parent.setdefault(leaf.parent_id, []).append(leaf)

    tree: list[DirectionTreeNode] = []
    for section in sections:
        children = [
            DirectionBase.model_validate(leaf)
            for leaf in by_parent.get(section.id, [])
        ]
        # Prefer catalog order from seed (slug order within section is fine for MVP)
        children.sort(key=lambda c: c.name)
        tree.append(
            DirectionTreeNode(
                id=section.id,
                name=section.name,
                slug=section.slug,
                description=section.description,
                professions=children,
            )
        )
    return tree
