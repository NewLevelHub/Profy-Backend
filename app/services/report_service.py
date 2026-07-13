import json
import logging
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
from app.models.profile import AgeGroup, Profile
from app.prompts import report_summary
from app.schemas.result import AnalysisResultResponse
from app.services import assessment_service, direction_service, llm_client
from app.services.ai_service import MatchedDirection, ReportDraft, generate_report

logger = logging.getLogger(__name__)

CACHE_TTL = 60 * 60 * 24  # 24 hours

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def _match_directions_full(
    total_scores: dict[str, float],
    db: AsyncSession,
    age_group: AgeGroup | None = None,
) -> list[MatchedDirection]:
    top = await direction_service.scored_directions(
        total_scores, db, age_group=age_group
    )
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
        for d, score in top
    ]


async def _generate_ai_summary(
    profile: Profile | None, goal: str, draft: ReportDraft, artifacts: list
) -> str | None:
    """AI-personalized result summary. Returns None (→ template) if disabled or fails."""
    if profile is None or not llm_client.is_enabled():
        return None
    try:
        messages = report_summary.build_messages(profile, goal, draft, artifacts)
        raw = await llm_client.complete_json(
            messages, report_summary.SUMMARY_SCHEMA, "report_summary"
        )
    except (llm_client.LLMError, TypeError):
        logger.warning("AI summary failed, using template summary")
        return None
    summary = raw.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return None


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
    wb_raw = await assessment_service.get_wellbeing_raw_scores(assessment_id, db)
    age_group = profile.age_group if profile else None
    matched = await _match_directions_full(total_scores, db, age_group)
    draft = generate_report(profile, artifacts, total_scores, matched, wb_raw_scores=wb_raw)
    summary = await _generate_ai_summary(profile, assessment.goal.value, draft, artifacts) or draft.summary

    analysis = AnalysisResult(
        assessment_id=assessment_id,
        summary=summary,
        strengths=draft.strengths,
        interests_map=draft.interests_map,
        thinking_style=draft.thinking_style,
        motivation=draft.motivation,
        directions=draft.directions,
        wellbeing_zones=draft.wellbeing_zones,
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
