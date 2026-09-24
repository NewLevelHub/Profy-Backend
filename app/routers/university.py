import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_optional
from app.i18n import get_locale
from app.models.user import User
from app.schemas.university import (
    ProgramBrief,
    ProgramDetail,
    UniversityCountry,
    UniversityDetail,
    UniversityListResponse,
)
from app.services.university_service import (
    add_favorite,
    get_program_detail,
    get_university_for_user,
    list_universities,
    list_university_countries,
    remove_favorite,
    search_programs_for_user,
)

router = APIRouter(tags=["universities"])


# NOTE ON ROUTE ORDER: every literal path below ("", "/countries", "/programs",
# "/favorites") must stay declared BEFORE "/{university_id}". FastAPI matches in
# declaration order, so a catch-all UUID parameter placed first would swallow
# "programs" and answer it with a 422 about an invalid UUID.


@router.get("", response_model=UniversityListResponse)
async def list_all_universities(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, description="Name, short name, city or alias"),
    country: str | None = Query(None),
    city: str | None = Query(None),
    only_favorites: bool = Query(False, description="Only the caller's starred universities"),
    sort: str | None = Query(None, description="ranking (default) | name | kz_rank"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
) -> UniversityListResponse:
    return await list_universities(
        db,
        user_id=current_user.id if current_user else None,
        page=page,
        limit=limit,
        search=search,
        country=country,
        city=city,
        only_favorites=only_favorites,
        sort=sort,
        order=order,
    )


@router.get("/countries", response_model=list[UniversityCountry])
async def list_countries(db: AsyncSession = Depends(get_db)) -> list[UniversityCountry]:
    return await list_university_countries(db)


@router.get("/programs", response_model=list[ProgramBrief])
async def list_programs(
    profession: str = Query(..., description="Direction (profession) slug, e.g. arhitektor"),
    country: str | None = Query(None, description="ISO country code or name, e.g. us or Kazakhstan"),
    limit: int = Query(10, ge=1, le=100),
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
) -> list[ProgramBrief]:
    # Optional auth, not required: this endpoint has always been public and
    # still answers without a token — a signed-in caller additionally gets
    # `is_favorite` filled in and their starred universities floated to the top.
    return await search_programs_for_user(
        db,
        profession_slug=profession,
        country=country,
        limit=limit,
        user_id=current_user.id if current_user else None,
        locale=get_locale(),
    )


@router.get("/programs/{program_id}", response_model=ProgramDetail)
async def get_program(
    program_id: uuid.UUID,
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
) -> ProgramDetail:
    return await get_program_detail(
        db,
        program_id,
        locale=get_locale(),
        user_id=current_user.id if current_user else None,
    )


@router.get("/{university_id}", response_model=UniversityDetail)
async def get_university(
    university_id: uuid.UUID,
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
) -> UniversityDetail:
    return await get_university_for_user(
        db, university_id, user_id=current_user.id if current_user else None
    )


@router.put("/{university_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
async def favorite_university(
    university_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    # PUT, not POST: starring is idempotent — the client is asserting a state
    # ("this is starred"), not appending an event.
    await add_favorite(db, current_user.id, university_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{university_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
async def unfavorite_university(
    university_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await remove_favorite(db, current_user.id, university_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
