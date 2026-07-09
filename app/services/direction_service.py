from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.direction import Direction
from app.models.profile import AgeGroup
from app.schemas.direction import DirectionBase, DirectionDetail, DirectionMatch


async def get_all_directions(db: AsyncSession) -> list[Direction]:
    result = await db.execute(select(Direction).order_by(Direction.name))
    return list(result.scalars().all())


async def get_direction_by_slug(slug: str, db: AsyncSession) -> Direction | None:
    result = await db.execute(select(Direction).where(Direction.slug == slug))
    return result.scalar_one_or_none()


def _fits_age(direction: Direction, age_group: AgeGroup | None) -> bool:
    """Whether a direction is offered to the given age group.

    age_group=None means "no age filtering". An unconfigured/empty age_groups
    list is treated as available to everyone (defensive)."""
    if age_group is None:
        return True
    groups = direction.age_groups or []
    if not groups:
        return True
    return age_group.value in groups


def score_direction(direction: Direction, scores: dict[str, float]) -> int | None:
    """Match score (0-99) of a direction against normalized scores.

    Returns None for directions without required_scores (unscoreable)."""
    required: dict[str, float] = direction.required_scores or {}
    if not required:
        return None
    bonus: dict[str, float] = direction.bonus_scores or {}

    req_scores = [
        min(scores.get(cat, 0) / threshold, 1.2)
        for cat, threshold in required.items()
    ]
    base = sum(req_scores) / len(req_scores)
    bonus_total = sum(
        (scores.get(cat, 0) / 100) * weight
        for cat, weight in bonus.items()
    )
    return min(round(base * 75 + bonus_total), 99)


async def scored_directions(
    scores: dict[str, float],
    db: AsyncSession,
    *,
    age_group: AgeGroup | None = None,
    limit: int = 5,
) -> list[tuple[Direction, int]]:
    """Single source of truth for direction matching: filter by age, score, rank."""
    directions = await get_all_directions(db)
    scored: list[tuple[Direction, int]] = []
    for direction in directions:
        if not _fits_age(direction, age_group):
            continue
        match_score = score_direction(direction, scores)
        if match_score is None:
            continue
        scored.append((direction, match_score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]


async def match_directions(
    scores: dict[str, float],
    db: AsyncSession,
    *,
    age_group: AgeGroup | None = None,
) -> list[DirectionMatch]:
    top = await scored_directions(scores, db, age_group=age_group)
    return [
        DirectionMatch(direction=DirectionBase.model_validate(d), match_score=score)
        for d, score in top
    ]


async def get_direction_details(slug: str, db: AsyncSession) -> DirectionDetail | None:
    direction = await get_direction_by_slug(slug, db)
    if direction is None:
        return None
    return DirectionDetail.model_validate(direction)
