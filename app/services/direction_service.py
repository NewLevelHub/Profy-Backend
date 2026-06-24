from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.direction import Direction
from app.schemas.direction import DirectionBase, DirectionDetail, DirectionMatch


async def get_all_directions(db: AsyncSession) -> list[Direction]:
    result = await db.execute(select(Direction).order_by(Direction.name))
    return list(result.scalars().all())


async def get_direction_by_slug(slug: str, db: AsyncSession) -> Direction | None:
    result = await db.execute(select(Direction).where(Direction.slug == slug))
    return result.scalar_one_or_none()


async def match_directions(
    scores: dict[str, float],
    db: AsyncSession,
) -> list[DirectionMatch]:
    directions = await get_all_directions(db)
    results: list[tuple[Direction, int]] = []

    for direction in directions:
        required: dict[str, float] = direction.required_scores or {}
        bonus: dict[str, float] = direction.bonus_scores or {}

        if not required:
            continue

        req_scores = [
            min(scores.get(cat, 0) / threshold, 1.2)
            for cat, threshold in required.items()
        ]
        base = sum(req_scores) / len(req_scores)

        bonus_total = sum(
            (scores.get(cat, 0) / 100) * weight
            for cat, weight in bonus.items()
        )

        match_score = min(round(base * 75 + bonus_total), 99)
        results.append((direction, match_score))

    results.sort(key=lambda x: x[1], reverse=True)
    top5 = results[:5]

    return [
        DirectionMatch(direction=DirectionBase.model_validate(d), match_score=score)
        for d, score in top5
    ]


async def get_direction_details(slug: str, db: AsyncSession) -> DirectionDetail | None:
    direction = await get_direction_by_slug(slug, db)
    if direction is None:
        return None
    return DirectionDetail.model_validate(direction)
