import json
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentStatus
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.schemas.gap import GapAnalysisResponse
from app.schemas.university import ProgramBrief, ProgramDetail
from app.services import assessment_service
from app.services.artifact_service import get_artifacts
from app.services.gap_analysis_service import analyze_gap, to_response
from app.services.university_service import get_program_by_id, search_programs

GAP_CACHE_TTL = 60 * 60  # 1 hour

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


router = APIRouter(tags=["universities"])


@router.get("/programs", response_model=list[ProgramBrief])
async def list_programs(
    direction: str = Query(
        ...,
        description=(
            "Comma-separated category slug(s), e.g. it-development or "
            "engineering-science,design-digital-art for professions that "
            "span more than one category"
        ),
    ),
    country: str | None = Query(None, description="ISO country code or name, e.g. us or Kazakhstan"),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[ProgramBrief]:
    direction_slugs = [slug.strip() for slug in direction.split(",") if slug.strip()]
    return await search_programs(db, direction_slugs=direction_slugs, country=country, limit=limit)


@router.get("/programs/{program_id}", response_model=ProgramDetail)
async def get_program(
    program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ProgramDetail:
    return await get_program_by_id(db, program_id)


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

    # Program.direction_slug is one of the ~10 curated categories, not a
    # profession slug — compare against category_slugs, not slug (see
    # scripts/specialty_category_lookup.py / Direction.category_slugs). A
    # profession can list more than one category (e.g. "Архитектор" spans
    # engineering-science and design-digital-art), so flatten them all.
    matched_categories = {
        category
        for d in analysis.careers
        if isinstance(d, dict)
        for category in d.get("category_slugs", [])
    }
    if program.direction_slug not in matched_categories:
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
