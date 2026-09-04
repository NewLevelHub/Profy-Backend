import uuid
from datetime import datetime, timezone
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.program import Program
from app.models.university import University
from app.schemas.admin_university import (
    AdminUniversityCountry,
    AdminUniversityListItem,
    AdminUniversityListResponse,
    AdminUniversityUpdateRequest,
    AdminProgramUpdateRequest,
)
from app.services.admin_lock import AdminNothingToClearError, lock_fields, unlock_fields
from app.services.admin_listing import SortOrder, order_by_clause, ru_text


# `programs_count` is an aggregate, not a column, so it can only be ordered by
# the same COUNT() the SELECT already computes — hence the separate entry.
_PROGRAMS_COUNT = func.count(Program.id)

UNIVERSITY_SORT_FIELDS = {
    # Russian-language columns need the ICU collation, or "sort by name" opens
    # on the Latin-named half of the catalog — see admin_listing.ru_text.
    "name": ru_text(University.name),
    "city": ru_text(University.city),
    "country": ru_text(University.country),
    "ranking": University.ranking,
    "uniranks_kz_rank": University.uniranks_kz_rank,
    "updated_at": University.updated_at,
    "programs_count": _PROGRAMS_COUNT,
}


def _search_clause(search: str):
    """Matches name, short name, city and any alias.

    Name-only search was the reason a university could not be found by its
    city or by the abbreviation everyone actually calls it — `aliases` is a
    JSONB array of strings, so each element is unnested and matched on its
    own rather than by pattern-matching the array's JSON text (which would
    also match punctuation and escapes).
    """
    like = f"%{search.strip()}%"
    alias = func.jsonb_array_elements_text(University.aliases).table_valued("value")
    alias_match = select(1).select_from(alias).where(alias.c.value.ilike(like)).exists()
    return or_(
        University.name.ilike(like),
        University.short_name.ilike(like),
        University.city.ilike(like),
        alias_match,
    )


async def list_universities(
    db: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    country: str | None = None,
    has_ranking: bool | None = None,
    has_programs: bool | None = None,
    sort: str | None = None,
    order: SortOrder | None = None,
) -> AdminUniversityListResponse:
    filters = []
    if search:
        filters.append(_search_clause(search))
    if country:
        filters.append(University.country == country)
    if has_ranking is not None:
        filters.append(
            University.ranking.isnot(None) if has_ranking else University.ranking.is_(None)
        )
    if has_programs is not None:
        # A university with no programs can be recommended to nobody — it is
        # invisible to students. Worth being able to list, not just to notice.
        clause = University.programs.any()
        filters.append(clause if has_programs else ~clause)

    # Total count
    total_result = await db.execute(select(func.count()).select_from(University).where(*filters))
    total = total_result.scalar_one()

    # Main query
    query = (
        select(University, _PROGRAMS_COUNT.label("programs_count"))
        .outerjoin(Program)
        .where(*filters)
        .group_by(University.id)
        .order_by(
            *order_by_clause(
                sort,
                order,
                allowed=UNIVERSITY_SORT_FIELDS,
                default=(ru_text(University.name).asc(),),
                tiebreaker=University.id.asc(),
            )
        )
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
                ranking_label=u.ranking_label,
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
    lock_fields(university, updates.keys())

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
    lock_fields(program, updates.keys())

    program.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(program)
    return program


async def _unlock_row(db: AsyncSession, row, field: str | None):
    """Put a hand-edited field back under seed control.

    A lock never recorded the value it replaced (only the field name), so
    unlocking restores nothing by itself — it makes the field eligible for
    the next seed run to overwrite, which is the only recovery path a lock
    has ever had. Reported as such rather than pretending to be an undo."""
    removed = unlock_fields(row, None if field is None else [field])
    if field is not None and not removed:
        raise AdminNothingToClearError(f"Field '{field}' is not locked on this row")

    await db.commit()
    await db.refresh(row)
    return row


async def unlock_university_fields(
    db: AsyncSession, university_id: uuid.UUID, field: str | None = None
) -> University:
    result = await db.execute(select(University).where(University.id == university_id))
    university = result.scalar_one_or_none()
    if university is None:
        raise ValueError("University not found")
    return await _unlock_row(db, university, field)


async def unlock_program_fields(
    db: AsyncSession, program_id: uuid.UUID, field: str | None = None
) -> Program:
    result = await db.execute(
        select(Program).options(selectinload(Program.university)).where(Program.id == program_id)
    )
    program = result.scalar_one_or_none()
    if program is None:
        raise ValueError("Program not found")
    return await _unlock_row(db, program, field)


async def list_countries(db: AsyncSession) -> list[AdminUniversityCountry]:
    """Every country present in the catalog, most-populated first.

    The country filter needs the full set of values, which a page of 20 rows
    cannot supply — the admin used to get it by downloading the whole catalog
    and counting client-side. One grouped query replaces that."""
    result = await db.execute(
        select(University.country, func.count())
        .group_by(University.country)
        .order_by(func.count().desc(), ru_text(University.country).asc())
    )
    return [
        AdminUniversityCountry(country=country, universities_count=count)
        for country, count in result.all()
    ]
