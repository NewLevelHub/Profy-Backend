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
    """Return Akinator sections with nested leaf professions, sorted by name."""
    result = await db.execute(select(Direction).order_by(Direction.name))
    all_dirs = list(result.scalars().all())

    sections = [d for d in all_dirs if not d.is_leaf and d.parent_id is None]
    leaves = [d for d in all_dirs if d.is_leaf]

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
