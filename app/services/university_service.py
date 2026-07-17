import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.program import Program
from app.models.university import University
from app.services.program_direction_resolver import program_direction_slugs_for


async def search_programs(
    db: AsyncSession,
    direction_slug: str,
    country: str | None = None,
    city: str | None = None,
    limit: int = 10,
) -> list[Program]:
    direction_slugs = await program_direction_slugs_for(direction_slug, db)
    query = (
        select(Program)
        .options(selectinload(Program.university))
        .join(Program.university)
        .where(Program.direction_slug.in_(direction_slugs))
    )
    if country is not None:
        query = query.where(University.country.ilike(country))
    if city is not None:
        query = query.where(University.city == city)
    query = query.limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_program_by_id(db: AsyncSession, program_id: uuid.UUID) -> Program:
    result = await db.execute(
        select(Program)
        .options(selectinload(Program.university))
        .where(Program.id == program_id)
    )
    program = result.scalar_one_or_none()
    if program is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found")
    return program
