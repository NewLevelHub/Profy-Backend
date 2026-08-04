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
from app.models.direction import Direction
from app.models.profile import Profile
from app.prompts import report_summary
from app.schemas.result import AnalysisResultResponse
from app.services import llm_client, riasec_service
from app.services.riasec_content import RIASEC_LABELS

logger = logging.getLogger(__name__)

CACHE_TTL = 60 * 60 * 24  # 24 hours

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _career_dict(direction: Direction, match_score: int) -> dict:
    return {
        "slug": direction.slug,
        "name": direction.name,
        "holland_code": direction.holland_code,
        "match_score": match_score,
        "description": direction.description or "",
        "professions": list(direction.professions or []),
        "skills_needed": list(direction.skills_needed or []),
        "subjects_to_develop": list(direction.subjects_to_develop or []),
        "first_steps": list(direction.first_steps or []),
    }


def _build_summary(code: list[str]) -> str:
    if not code:
        return "Твои результаты показывают широкий потенциал для развития."
    labels = [RIASEC_LABELS.get(letter, letter) for letter in code]
    code_str = "".join(code)
    if len(labels) == 1:
        cats_str = labels[0]
    else:
        cats_str = ", ".join(labels[:-1]) + " и " + labels[-1]
    return (
        f"Твой код RIASEC — {code_str}. Сильнее всего у тебя выражены типы: {cats_str}. "
        f"Это подсказывает, в какую сторону тебе интересно и комфортно развиваться."
    )


async def _generate_ai_summary(
    profile: Profile | None,
    goal: str,
    code: list[str],
    strengths: list[str],
    careers: list[dict],
    artifacts: list,
) -> str | None:
    """AI-personalized result summary. Returns None (→ template) if disabled or fails."""
    if profile is None or not llm_client.is_enabled():
        return None
    try:
        messages = report_summary.build_messages(profile, goal, code, strengths, careers, artifacts)
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

    raw = await riasec_service.raw_scores(assessment_id, db)
    counts = await riasec_service.question_counts(db)
    profile_scores = riasec_service.normalize(raw, counts)
    aversion_counts = await riasec_service.aversion(assessment_id, db)

    code = riasec_service.top_code(profile_scores)
    meta = {
        "differentiation": riasec_service.differentiation(profile_scores),
        "consistency": riasec_service.consistency(code[:2]),
        "aversion": aversion_counts,
    }
    strengths, weaknesses = riasec_service.strengths_weaknesses(profile_scores, aversion_counts, counts)
    plan = riasec_service.development_plan(code, weaknesses, aversion_counts, counts)

    matched = await riasec_service.matched_careers(code, db)
    careers = [_career_dict(d, score) for d, score in matched]

    template_summary = _build_summary(code)
    ai_summary = await _generate_ai_summary(
        profile, assessment.goal.value, code, strengths, careers, artifacts
    )
    summary = ai_summary or template_summary

    analysis = AnalysisResult(
        assessment_id=assessment_id,
        summary=summary,
        profile=profile_scores,
        code=code,
        meta=meta,
        careers=careers,
        strengths=strengths,
        weaknesses=weaknesses,
        development_plan=plan,
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
