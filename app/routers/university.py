import json
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_optional
from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentStatus
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.schemas.gap import GapAnalysisResponse
from app.schemas.university import (
    ProgramBrief,
    ProgramDetail,
    UniversityCountry,
    UniversityDetail,
    UniversityListResponse,
)
from app.services import assessment_service
from app.services.artifact_service import get_artifacts
from app.services.gap_analysis_service import analyze_gap, to_response
from app.services.university_service import (
    add_favorite,
    get_program_by_id,
    get_program_detail,
    get_university_for_user,
    list_universities,
    list_university_countries,
    remove_favorite,
    search_programs_for_user,
)

GAP_CACHE_TTL = 60 * 60  # 1 hour

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


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
    )


@router.get("/programs/{program_id}", response_model=ProgramDetail)
async def get_program(
    program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ProgramDetail:
    return await get_program_detail(db, program_id)


@router.get("/programs/{program_id}/gap-analysis", response_model=GapAnalysisResponse)
async def get_gap_analysis(
    program_id: uuid.UUID,
    assessment_id: uuid.UUID = Query(..., description="Assessment ID to use for scores"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GapAnalysisResponse:
    profile_result = await db.execute(select(Profile).where(Profile.user_id == current_user.id))
    profile = profile_result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    if profile.age_group != AgeGroup.senior:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Gap analysis is only available for senior age group",
        )

    cache_key = f"gap_analysis:{program_id}:{assessment_id}"
    redis = _get_redis()
    cached = await redis.get(cache_key)
    if cached:
        return GapAnalysisResponse.model_validate_json(cached)

    program = await get_program_by_id(db, program_id)

    assessment_result = await db.execute(
        select(Assessment).where(
            Assessment.id == assessment_id,
            Assessment.profile_id == profile.id,
        )
    )
    assessment = assessment_result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    if assessment.status != AssessmentStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assessment is not completed yet",
        )

    analysis_result = await db.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
    )
    analysis = analysis_result.scalar_one_or_none()
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Generate a report for this assessment before running gap analysis",
        )

    # Program.profession_slugs directly lists which professions (Direction
    # slugs) this specialty prepares someone for — check whether any of the
    # user's matched professions overlap with it.
    matched_profession_slugs = {d["slug"] for d in analysis.careers if isinstance(d, dict) and "slug" in d}
    if not matched_profession_slugs.intersection(program.profession_slugs):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This program's direction does not match your assessment results",
        )

    artifacts = await get_artifacts(profile.id, db)
    scores = await assessment_service.get_total_scores(assessment_id, db)

    result = analyze_gap(profile, artifacts, scores, program)
    response = to_response(program_id, result)

    await redis.set(cache_key, response.model_dump_json(), ex=GAP_CACHE_TTL)

    return response


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
