import json
import logging
import uuid
from dataclasses import dataclass

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.assessment import Assessment
from app.models.direction_roadmap import DirectionRoadmap
from app.models.profile import AgeGroup, Profile
from app.models.subject_readiness_session import SubjectReadinessSession, SubjectReadinessStatus
from app.prompts import direction_roadmap as direction_prompt
from app.schemas.roadmap import (
    DIRECTION_HORIZONS,
    DirectionRoadmapResponse,
    DirectionStage,
    GrowthFocus,
    RoadmapTarget,
    UniversityTrack,
)
from app.schemas.student_context import StudentContext
from app.services import direction_service, llm_client
from app.services.student_context import build_student_context

logger = logging.getLogger(__name__)

CACHE_TTL = 60 * 60 * 24  # 24 hours

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


_AI_UNAVAILABLE = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="ИИ временно недоступен, попробуй ещё раз",
)


@dataclass
class _DirectionPlan:
    """The LLM's plan, validated — everything the roadmap row needs."""

    target: RoadmapTarget
    growth_focus: GrowthFocus
    stages: list[DirectionStage]
    skills_to_build: list[str]
    subjects_to_focus: list[str]
    university_track: UniversityTrack


def direction_cache_key(assessment_id: uuid.UUID, slug: str) -> str:
    return f"droadmap:{assessment_id}:{slug}"


_MIN_STEPS_PER_STAGE = 3


def _valid_stages(stages: list[DirectionStage]) -> bool:
    """Structure guard: all 4 horizons exactly once, every stage has enough steps."""
    if len(stages) != len(DIRECTION_HORIZONS):
        return False
    if {s.horizon for s in stages} != set(DIRECTION_HORIZONS):
        return False
    for stage in stages:
        if len(stage.steps) < _MIN_STEPS_PER_STAGE:
            return False
        tracks = {step.track for step in stage.steps}
        if not tracks & {"profile", "integration"}:
            return False
        if not tracks & {"growth", "integration"}:
            return False
    return True


async def _require_direction_roadmap_access(
    assessment_id: uuid.UUID, slug: str, db: AsyncSession
) -> tuple[Assessment, object]:
    assessment = (
        await db.execute(select(Assessment).where(Assessment.id == assessment_id))
    ).scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    profile = (
        await db.execute(select(Profile).where(Profile.id == assessment.profile_id))
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    if profile.age_group == AgeGroup.junior:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Эта возможность доступна с 10 лет",
        )
    # Direction roadmap generation is goal-agnostic — `goal` already rides
    # along inside StudentContext (see student_context.py) and shapes the
    # LLM prompt, so a university-bound student gets a plan that reads that
    # way, same underlying builder. There is no separate program-specific
    # plan feature in this codebase to defer to instead — "Найти университеты"
    # (a plain program search) is a different, already-independent action.

    if assessment.selected_direction_slug != slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сначала выберите это направление в тесте",
        )

    direction = await direction_service.get_direction_by_slug(slug, db)
    if direction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Direction not found")

    return assessment, direction


_MAX_PLAN_ATTEMPTS = 2


async def _generate_plan(context: StudentContext, direction) -> _DirectionPlan | None:
    messages = direction_prompt.build_messages(context, direction)

    for attempt in range(1, _MAX_PLAN_ATTEMPTS + 1):
        try:
            raw = await llm_client.complete_json(
                messages,
                direction_prompt.DIRECTION_ROADMAP_SCHEMA,
                "direction_roadmap",
                timeout=settings.LLM_ROADMAP_TIMEOUT,
                max_tokens=settings.LLM_ROADMAP_MAX_TOKENS,
            )
            plan = _DirectionPlan(
                target=RoadmapTarget.model_validate(raw.get("target", {})),
                growth_focus=GrowthFocus.model_validate(raw.get("growth_focus", {})),
                stages=[DirectionStage.model_validate(s) for s in raw.get("stages", [])],
                skills_to_build=list(raw.get("skills_to_build", [])),
                subjects_to_focus=list(raw.get("subjects_to_focus", [])),
                university_track=UniversityTrack.model_validate(
                    raw.get("university_track", {})
                ),
            )
        except (llm_client.LLMError, ValidationError, TypeError) as exc:
            logger.warning("Direction roadmap generation failed: %s", exc)
            return None

        if _valid_stages(plan.stages):
            return plan

        logger.warning(
            "Direction roadmap failed invariant check (attempt %s/%s)",
            attempt, _MAX_PLAN_ATTEMPTS,
        )
        messages = [*messages, direction_prompt.RETRY_HINT]

    return None


async def generate_direction_roadmap(
    assessment_id: uuid.UUID, slug: str, db: AsyncSession
) -> DirectionRoadmapResponse:
    if not llm_client.is_enabled():
        raise _AI_UNAVAILABLE

    redis = _get_redis()
    key = direction_cache_key(assessment_id, slug)
    cached = await redis.get(key)
    if cached:
        return DirectionRoadmapResponse.model_validate_json(cached)

    assessment, direction = await _require_direction_roadmap_access(assessment_id, slug, db)

    context = await build_student_context(assessment_id, db, direction_slug=slug)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    plan = await _generate_plan(context, direction)
    if plan is None:
        raise _AI_UNAVAILABLE

    roadmap = await _upsert_direction_roadmap(assessment_id, slug, direction.name, plan, db)
    assessment.selected_direction_slug = slug
    await db.commit()
    await db.refresh(roadmap)

    response = DirectionRoadmapResponse.model_validate(roadmap)
    await redis.setex(key, CACHE_TTL, response.model_dump_json())
    return response


async def _measured_subjects_to_focus(
    assessment_id: uuid.UUID, db: AsyncSession
) -> list[str] | None:
    """Growth-area subjects from a completed subject readiness quiz (see
    app/services/subject_readiness_service.py), if the student has taken one
    for this assessment — grounds subjects_to_focus in a measured signal
    instead of the LLM's guess. None if no completed quiz exists yet."""
    session = (
        await db.execute(
            select(SubjectReadinessSession).where(
                SubjectReadinessSession.assessment_id == assessment_id,
                SubjectReadinessSession.status == SubjectReadinessStatus.completed,
            )
        )
    ).scalar_one_or_none()
    if session is None:
        return None
    growth_subjects = [
        subject
        for subject, scores in session.subject_scores.items()
        if not scores.get("is_strength")
    ]
    return growth_subjects or None


async def _upsert_direction_roadmap(
    assessment_id: uuid.UUID,
    slug: str,
    direction_name: str,
    plan: "_DirectionPlan",
    db: AsyncSession,
) -> DirectionRoadmap:
    existing = (
        await db.execute(
            select(DirectionRoadmap).where(
                DirectionRoadmap.assessment_id == assessment_id,
                DirectionRoadmap.direction_slug == slug,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        roadmap = DirectionRoadmap(
            assessment_id=assessment_id,
            direction_slug=slug,
            direction_name=direction_name,
        )
        db.add(roadmap)
    else:
        roadmap = existing

    roadmap.direction_name = direction_name
    roadmap.target = plan.target.model_dump()
    roadmap.growth_focus = plan.growth_focus.model_dump()
    roadmap.stages = [s.model_dump() for s in plan.stages]
    roadmap.skills_to_build = plan.skills_to_build
    measured_subjects = await _measured_subjects_to_focus(assessment_id, db)
    roadmap.subjects_to_focus = (
        measured_subjects if measured_subjects is not None else plan.subjects_to_focus
    )
    roadmap.university_track = plan.university_track.model_dump()
    return roadmap


async def get_direction_roadmap(
    assessment_id: uuid.UUID, slug: str, db: AsyncSession
) -> DirectionRoadmapResponse | None:
    redis = _get_redis()
    key = direction_cache_key(assessment_id, slug)

    cached = await redis.get(key)
    if cached:
        return DirectionRoadmapResponse.model_validate_json(cached)

    roadmap = (
        await db.execute(
            select(DirectionRoadmap).where(
                DirectionRoadmap.assessment_id == assessment_id,
                DirectionRoadmap.direction_slug == slug,
            )
        )
    ).scalar_one_or_none()
    if roadmap is None:
        return None

    response = DirectionRoadmapResponse.model_validate(roadmap)
    await redis.setex(key, CACHE_TTL, response.model_dump_json())
    return response
