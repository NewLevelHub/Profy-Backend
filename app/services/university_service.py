import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.direction import Direction
from app.models.program import Program
from app.models.university import University
from app.schemas.university import ProgramDetail, UniversityBrief
from app.services import university_requirements as ureq


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
        .join(Program.directions)
        .where(Direction.slug == profession_slug)
    )
    if country is not None:
        query = query.where(University.country.ilike(country))
    # Best-known university first. University.ranking is the QS World numeric
    # position (parsed from ranking_label's "#N (QS World ...)" prefix) — the
    # only rank scale comparable across countries — so it sorts first;
    # uniranks_world_rank (KZ-market source, mostly populated for KZ
    # universities that have no QS World number) is the tiebreak for
    # everything QS didn't rank. Universities with neither sort last, in a
    # stable name order rather than DB-arbitrary order.
    query = query.order_by(
        University.ranking.asc().nulls_last(),
        University.uniranks_world_rank.asc().nulls_last(),
        University.name.asc(),
    )
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


async def get_program_detail(db: AsyncSession, program_id: uuid.UUID) -> ProgramDetail:
    """`ProgramDetail`, ready for the client — `requirements_summary` is the
    same clean, typed mapping the direction-roadmap prompt uses
    (app/services/university_requirements.py), not a re-derivation. Separate
    from `get_program_by_id` because that one returns the raw ORM `Program`
    for callers that need it as-is (gap-analysis)."""
    program = await get_program_by_id(db, program_id)
    return ProgramDetail(
        id=program.id,
        name=program.name,
        profession_slugs=program.profession_slugs,
        language=program.language,
        cost_per_year=program.cost_per_year,
        cost_label=program.cost_label,
        description=program.description,
        who_its_for=program.who_its_for,
        career_options=program.career_options,
        requirements=program.requirements,
        deadlines=program.deadlines,
        grants=program.grants,
        created_at=program.created_at,
        university=UniversityBrief.model_validate(program.university),
        requirements_summary=ureq.map_program_requirement(program, program.university),
    )
