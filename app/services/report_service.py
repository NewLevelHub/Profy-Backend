import json
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.analysis_result import AnalysisResult
from app.models.artifact import Artifact
from app.models.assessment import Assessment, AssessmentStatus
from app.models.direction import Direction
from app.models.profile import Profile
from app.schemas.result import AnalysisResultResponse
from app.services import assessment_service
from app.services.ai_service import MatchedDirection, generate_report

CACHE_TTL = 60 * 60 * 24  # 24 hours

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def _match_directions_full(
    total_scores: dict[str, float], db: AsyncSession
) -> list[MatchedDirection]:
    result = await db.execute(select(Direction).order_by(Direction.name))
    directions = list(result.scalars().all())

    scored: list[tuple[Direction, int]] = []
    for direction in directions:
        required: dict[str, float] = direction.required_scores or {}
        bonus: dict[str, float] = direction.bonus_scores or {}
        if not required:
            continue
        req_scores = [
            min(total_scores.get(cat, 0) / threshold, 1.2)
            for cat, threshold in required.items()
        ]
        base = sum(req_scores) / len(req_scores)
        bonus_total = sum(
            (total_scores.get(cat, 0) / 100) * weight
            for cat, weight in bonus.items()
        )
        match_score = min(round(base * 75 + bonus_total), 99)
        scored.append((direction, match_score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [
        MatchedDirection(
            slug=d.slug,
            name=d.name,
            match_score=score,
            description=d.description or "",
            professions=list(d.professions or []),
            skills_needed=list(d.skills_needed or []),
            subjects_to_develop=list(d.subjects_to_develop or []),
            first_steps=list(d.first_steps or []),
            required_scores=dict(d.required_scores or {}),
        )
        for d, score in scored[:5]
    ]


async def build_report(
    assessment_id: uuid.UUID, db: AsyncSession
) -> AnalysisResultResponse:
    cache_key = f"report:{assessment_id}"
    redis = _get_redis()

    cached = await redis.get(cache_key)
    if cached:
        return AnalysisResultResponse.model_validate(json.loads(cached))

    existing_result = await db.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        response = AnalysisResultResponse.model_validate(existing)
        await redis.setex(cache_key, CACHE_TTL, response.model_dump_json())
        return response

    assessment_result = await db.execute(
        select(Assessment).where(Assessment.id == assessment_id)
    )
    assessment = assessment_result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found"
        )

    if assessment.status != AssessmentStatus.completed:
        assessment.status = AssessmentStatus.completed
        assessment.completed_at = datetime.now(timezone.utc)
        await db.commit()

    profile_result = await db.execute(
        select(Profile).where(Profile.id == assessment.profile_id)
    )
    profile = profile_result.scalar_one_or_none()

    artifacts_result = await db.execute(
        select(Artifact).where(Artifact.profile_id == assessment.profile_id)
    )
    artifacts = list(artifacts_result.scalars().all())

    total_scores = await assessment_service.get_total_scores(assessment_id, db)
    matched = await _match_directions_full(total_scores, db)
    draft = generate_report(profile, artifacts, total_scores, matched)

    analysis = AnalysisResult(
        assessment_id=assessment_id,
        summary=draft.summary,
        strengths=draft.strengths,
        interests_map=draft.interests_map,
        thinking_style=draft.thinking_style,
        motivation=draft.motivation,
        directions=draft.directions,
    )
    db.add(analysis)
    try:
        await db.commit()
        await db.refresh(analysis)
    except IntegrityError:
        await db.rollback()
        existing_result = await db.execute(
            select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
        )
        analysis = existing_result.scalar_one()

    response = AnalysisResultResponse.model_validate(analysis)
    await redis.setex(cache_key, CACHE_TTL, response.model_dump_json())
    return response


async def get_report(
    assessment_id: uuid.UUID, db: AsyncSession
) -> AnalysisResultResponse | None:
    cache_key = f"report:{assessment_id}"
    redis = _get_redis()

    cached = await redis.get(cache_key)
    if cached:
        return AnalysisResultResponse.model_validate(json.loads(cached))

    result = await db.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        return None
    response = AnalysisResultResponse.model_validate(analysis)
    await redis.setex(cache_key, CACHE_TTL, response.model_dump_json())
    return response
