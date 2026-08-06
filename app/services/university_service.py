import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.program import Program
from app.models.university import University


async def search_programs(
    db: AsyncSession,
    profession_slug: str,
    country: str | None = None,
    limit: int = 10,
) -> list[Program]:
    query = (
        select(Program)
        .options(selectinload(Program.university))
        .join(Program.university)
        .where(Program.profession_slugs.contains([profession_slug]))
    )
    if country is not None:
        query = query.where(University.country.ilike(country))
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
