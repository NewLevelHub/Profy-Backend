import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.i18n import DEFAULT_LOCALE, resolve_column_i18n
from app.models.direction import Direction
from app.models.program import Program
from app.models.university import University
from app.schemas.university import ProgramBrief, ProgramDetail, UniversityBrief
from app.services import university_requirements as ureq


def _university_brief(university: University, locale: str) -> UniversityBrief:
    """`UniversityBrief` with `description` resolved for `locale` (KZ-501):
    the `kk` override when present, else the `ru` base column, with
    `description_locale` reporting which was served."""
    description, description_locale = resolve_column_i18n(
        university.description_i18n, university.description, locale
    )
    return UniversityBrief.model_validate(university).model_copy(
        update={"description": description, "description_locale": description_locale}
    )


def _program_brief(program: Program, locale: str) -> ProgramBrief:
    description, description_locale = resolve_column_i18n(
        program.description_i18n, program.description, locale
    )
    return ProgramBrief.model_validate(program).model_copy(
        update={
            "description": description,
            "description_locale": description_locale,
            "university": _university_brief(program.university, locale),
        }
    )


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


async def list_program_briefs(
    db: AsyncSession,
    profession_slug: str,
    country: str | None = None,
    limit: int = 10,
    locale: str = DEFAULT_LOCALE,
) -> list[ProgramBrief]:
    """`search_programs` shaped into `ProgramBrief`, with each program's and
    its university's `description` resolved for `locale` (KZ-501)."""
    programs = await search_programs(db, profession_slug, country, limit)
    return [_program_brief(program, locale) for program in programs]


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
    db: AsyncSession, program_id: uuid.UUID, locale: str = DEFAULT_LOCALE
) -> ProgramDetail:
    """`ProgramDetail`, ready for the client — `requirements_summary` is the
    same clean, typed mapping the direction-roadmap prompt uses
    (app/services/university_requirements.py), not a re-derivation. Separate
    from `get_program_by_id` because that one returns the raw ORM `Program`
    for callers that need it as-is (gap-analysis).

    `description` / `who_its_for` are resolved for `locale` (KZ-501): the `kk`
    override when present, else the `ru` base column, with `*_locale` fields
    reporting which was served."""
    program = await get_program_by_id(db, program_id)
    description, description_locale = resolve_column_i18n(
        program.description_i18n, program.description, locale
    )
    who_its_for, who_its_for_locale = resolve_column_i18n(
        program.who_its_for_i18n, program.who_its_for, locale
    )
    return ProgramDetail(
        id=program.id,
        name=program.name,
        profession_slugs=program.profession_slugs,
        language=program.language,
        cost_per_year=program.cost_per_year,
        cost_label=program.cost_label,
        description=description,
        description_locale=description_locale,
        who_its_for=who_its_for,
        who_its_for_locale=who_its_for_locale,
        career_options=program.career_options,
        requirements=program.requirements,
        deadlines=program.deadlines,
        grants=program.grants,
        created_at=program.created_at,
        university=_university_brief(program.university, locale),
        requirements_summary=ureq.map_program_requirement(program, program.university),
    )
