import uuid
from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.program import Program
from app.models.university import University
from app.schemas.admin_university import (
    AdminUniversityListItem,
    AdminUniversityListResponse,
    AdminUniversityUpdateRequest,
    AdminProgramUpdateRequest,
)


async def list_universities(
    db: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
) -> AdminUniversityListResponse:
    filters = []
    if search:
        filters.append(University.name.ilike(f"%{search.strip()}%"))

    # Total count
    total_result = await db.execute(select(func.count()).select_from(University).where(*filters))
    total = total_result.scalar_one()

    # Main query
    query = (
        select(University, func.count(Program.id).label("programs_count"))
        .outerjoin(Program)
        .where(*filters)
        .group_by(University.id)
        .order_by(University.name.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(query)
    
    items = []
    for u, count in result.all():
        items.append(
            AdminUniversityListItem(
                id=u.id,
                name=u.name,
                city=u.city,
                country=u.country,
                ranking=u.ranking,
                uniranks_kz_rank=u.uniranks_kz_rank,
                uniranks_note=u.uniranks_note,
                updated_at=u.updated_at,
                programs_count=count,
            )
        )

    return AdminUniversityListResponse(items=items, total=total, page=page, limit=limit)


async def get_university_detail(db: AsyncSession, university_id: uuid.UUID) -> University | None:
    # Since programs is lazy="selectin" on the model, it is loaded automatically.
    # We query University and return it.
    result = await db.execute(select(University).where(University.id == university_id))
    return result.scalar_one_or_none()


async def update_university(
    db: AsyncSession,
    university_id: uuid.UUID,
    data: AdminUniversityUpdateRequest,
) -> University:
    result = await db.execute(select(University).where(University.id == university_id))
    university = result.scalar_one_or_none()
    if university is None:
        raise ValueError("University not found")

    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(university, key, value)

    university.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(university)
    return university


async def update_program(
    db: AsyncSession,
    program_id: uuid.UUID,
    data: AdminProgramUpdateRequest,
) -> Program:
    result = await db.execute(
        select(Program)
        .options(selectinload(Program.university))
        .where(Program.id == program_id)
    )
    program = result.scalar_one_or_none()
    if program is None:
        raise ValueError("Program not found")

    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(program, key, value)

    program.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(program)
    return program
