import uuid

from fastapi import HTTPException, status
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload, selectinload

from app.models.direction import Direction
from app.models.program import Program
from app.models.university import University
from app.models.university_favorite import UniversityFavorite
from app.schemas.university import (
    ProgramBrief,
    ProgramDetail,
    UniversityBrief,
    UniversityCountry,
    UniversityDetail,
    UniversityListItem,
    UniversityListResponse,
)
from app.services import university_requirements as ureq

# Catalogue sort keys the client may ask for. Anything else is rejected
# rather than silently ignored, so a typo in the query string surfaces as a
# 422 instead of a quietly wrong order.
UNIVERSITY_SORT_FIELDS = {
    "name": University.name,
    "ranking": University.ranking,
    "kz_rank": University.uniranks_kz_rank,
}


def _favorite_ids_select(user_id: uuid.UUID):
    return select(UniversityFavorite.university_id).where(UniversityFavorite.user_id == user_id)


def _favorite_first_clause(user_id: uuid.UUID | None):
    """Ordering term that floats the caller's starred universities to the top.

    Returned as a one-element list (or an empty one for anonymous callers) so
    callers can splat it in front of their own ORDER BY chain without
    branching on None.
    """
    if user_id is None:
        return []
    return [case((University.id.in_(_favorite_ids_select(user_id)), 0), else_=1).asc()]


def _search_clause(search: str):
    """Matches name, short name, city and any alias.

    Name-only search is why a university can't be found by the abbreviation
    everyone actually calls it, or by its city. `aliases` is a JSONB array of
    strings, so each element is unnested and matched on its own rather than
    pattern-matching the array's JSON text (which would also match
    punctuation and escapes).
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


def _catalogue_order_by(sort: str | None, order: str):
    descending = order == "desc"
    if sort is None or sort == "ranking":
        # The catalogue's default. `ranking` (QS world position) is the only
        # scale comparable across countries; uniranks_world_rank breaks the
        # tie for everything QS never ranked. Universities with neither sort
        # last in either direction — they are unranked, not "worst", so they
        # must never be blended into the middle by a fallback score.
        direction = (lambda col: col.desc()) if descending else (lambda col: col.asc())
        return [
            direction(University.ranking).nulls_last(),
            direction(University.uniranks_world_rank).nulls_last(),
            University.name.asc(),
        ]
    column = UNIVERSITY_SORT_FIELDS.get(sort)
    if column is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "detail": f"Unknown sort field: {sort}",
                "allowed_sort_fields": sorted(UNIVERSITY_SORT_FIELDS),
            },
        )
    ordered = column.desc().nulls_last() if descending else column.asc().nulls_last()
    return [ordered]


async def search_programs(
    db: AsyncSession,
    profession_slug: str,
    country: str | None = None,
    limit: int = 10,
    user_id: uuid.UUID | None = None,
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
    # Starred universities first (PRO-265) — the student already told us these
    # matter, so a better-ranked school they did not pick should not bury
    # them. Everything after this term is the untouched catalogue-quality
    # ordering below.
    query = query.order_by(
        *_favorite_first_clause(user_id),
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


async def get_program_detail(
    db: AsyncSession,
    program_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> ProgramDetail:
    """`ProgramDetail`, ready for the client — `requirements_summary` is the
    same clean, typed mapping the direction-roadmap prompt uses
    (app/services/university_requirements.py), not a re-derivation. Separate
    from `get_program_by_id` because that one returns the raw ORM `Program`
    for callers that need it as-is (gap-analysis)."""
    program = await get_program_by_id(db, program_id)
    favorite_ids = await favorite_university_ids(db, user_id) if user_id else set()
    university = _brief_with_favorite(program.university, favorite_ids)
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
        university=university,
        requirements_summary=ureq.map_program_requirement(program, program.university),
        cost_currency=program.cost_currency,
        cost_per_year_min=program.cost_per_year_min,
        cost_per_year_max=program.cost_per_year_max,
    )


async def favorite_university_ids(db: AsyncSession, user_id: uuid.UUID) -> set[uuid.UUID]:
    result = await db.execute(_favorite_ids_select(user_id))
    return set(result.scalars().all())


def _brief_with_favorite(university: University, favorite_ids: set[uuid.UUID]) -> UniversityBrief:
    brief = UniversityBrief.model_validate(university)
    brief.is_favorite = university.id in favorite_ids
    return brief


async def search_programs_for_user(
    db: AsyncSession,
    profession_slug: str,
    country: str | None = None,
    limit: int = 10,
    user_id: uuid.UUID | None = None,
) -> list[ProgramBrief]:
    """`search_programs`, mapped to the wire schema with `is_favorite` filled in.

    The router used to hand FastAPI the raw ORM rows and let `from_attributes`
    do the mapping, but `is_favorite` is per-caller and has no ORM column
    behind it — it has to be stamped on after validation, which needs the
    mapping to happen here rather than in the response-model layer.
    """
    programs = await search_programs(
        db, profession_slug=profession_slug, country=country, limit=limit, user_id=user_id
    )
    favorite_ids = await favorite_university_ids(db, user_id) if user_id else set()
    briefs = []
    for program in programs:
        brief = ProgramBrief.model_validate(program)
        brief.university.is_favorite = program.university_id in favorite_ids
        briefs.append(brief)
    return briefs


async def list_universities(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None = None,
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    country: str | None = None,
    city: str | None = None,
    only_favorites: bool = False,
    sort: str | None = None,
    order: str = "asc",
) -> UniversityListResponse:
    """The standalone catalogue (PRO-265).

    Paginated with a {items, total, page, limit} envelope rather than the
    bare, unpaginated array the other public list endpoints return — this
    one lists the whole university table, so "just send everything" is not
    an option.
    """
    filters = []
    if search:
        filters.append(_search_clause(search))
    if country:
        filters.append(University.country == country)
    if city:
        filters.append(University.city == city)
    if only_favorites:
        # An anonymous caller has no favourites, so this legitimately yields
        # an empty page rather than an error.
        if user_id is None:
            return UniversityListResponse(items=[], total=0, page=page, limit=limit)
        filters.append(University.id.in_(_favorite_ids_select(user_id)))

    total_result = await db.execute(select(func.count()).select_from(University).where(*filters))
    total = total_result.scalar_one()

    programs_count = func.count(Program.id)
    query = (
        select(University, programs_count.label("programs_count"))
        # Catalogue rows only need the University columns + the aggregate
        # count — without these noloads, selectin on `images` / `programs`
        # (and then Program.directions) fires three extra round-trips per
        # page for data the response never serializes.
        .options(noload(University.images), noload(University.programs))
        .outerjoin(Program)
        .where(*filters)
        .group_by(University.id)
        .order_by(
            *_favorite_first_clause(user_id),
            *_catalogue_order_by(sort, order),
            # OFFSET pagination over a non-unique sort key can otherwise drop
            # or repeat rows between pages.
            University.id.asc(),
        )
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(query)
    rows = result.all()

    favorite_ids = await favorite_university_ids(db, user_id) if user_id else set()
    items = []
    for university, count in rows:
        item = UniversityListItem.model_validate(university)
        item.is_favorite = university.id in favorite_ids
        item.programs_count = count
        items.append(item)

    return UniversityListResponse(items=items, total=total, page=page, limit=limit)


async def list_university_countries(db: AsyncSession) -> list[UniversityCountry]:
    """Only countries actually present in the table — a static list would
    offer filters with nothing behind them."""
    result = await db.execute(
        select(University.country, func.count(University.id))
        .group_by(University.country)
        .order_by(University.country.asc())
    )
    return [UniversityCountry(country=country, count=count) for country, count in result.all()]


async def get_university_for_user(
    db: AsyncSession,
    university_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> UniversityDetail:
    # `Program.university` has to be eager-loaded explicitly: University.programs
    # is lazy="selectin", but the back-reference on each loaded Program is not,
    # and ProgramBrief needs it — touching it lazily inside async would raise
    # MissingGreenlet instead of quietly issuing a query.
    result = await db.execute(
        select(University)
        .options(selectinload(University.programs).selectinload(Program.university))
        .where(University.id == university_id)
    )
    university = result.scalar_one_or_none()
    if university is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="University not found")

    favorite_ids = await favorite_university_ids(db, user_id) if user_id else set()
    is_favorite = university.id in favorite_ids

    programs = []
    for program in university.programs:
        brief = ProgramBrief.model_validate(program)
        brief.university.is_favorite = is_favorite
        programs.append(brief)

    # Built field-by-field rather than model_validate(university): UniversityDetail
    # declares `programs`, and from_attributes would re-derive them from the ORM
    # relationship without the `is_favorite` stamping above.
    return UniversityDetail(
        **_brief_with_favorite(university, favorite_ids).model_dump(),
        contacts=university.contacts,
        facilities=university.facilities,
        source_url=university.source_url,
        programs=programs,
    )


async def _require_university(db: AsyncSession, university_id: uuid.UUID) -> University:
    result = await db.execute(select(University).where(University.id == university_id))
    university = result.scalar_one_or_none()
    if university is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="University not found")
    return university


async def add_favorite(db: AsyncSession, user_id: uuid.UUID, university_id: uuid.UUID) -> None:
    """Star a university. Idempotent: starring twice is a no-op, not a 409.

    ON CONFLICT DO NOTHING rather than SELECT-then-INSERT — two clicks racing
    each other would both pass the check and one would then blow up on the
    unique constraint.
    """
    await _require_university(db, university_id)
    await db.execute(
        pg_insert(UniversityFavorite)
        .values(user_id=user_id, university_id=university_id)
        .on_conflict_do_nothing(constraint="uq_university_favorites_user_university")
    )
    await db.commit()


async def remove_favorite(db: AsyncSession, user_id: uuid.UUID, university_id: uuid.UUID) -> None:
    """Unstar a university. Idempotent for the same reason as add_favorite:
    the caller asked for "not starred", and it already isn't."""
    await _require_university(db, university_id)
    await db.execute(
        delete(UniversityFavorite).where(
            UniversityFavorite.user_id == user_id,
            UniversityFavorite.university_id == university_id,
        )
    )
    await db.commit()
