"""Development plan generation — orchestration, validation, cache, persistence.

Two LLM phases (see app/prompts/development_plan.py):
  1. skeleton  — one call: target, about_you, skills, 4 stages of bare tasks
  2. expand    — one call per stage (gathered): fills steps[] -> actions[]

No template fallback: LLM off or a phase that stays broken after one retry
returns 503.
"""
import asyncio
import json
import logging
import uuid

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.assessment import Assessment
from app.models.development_plan import DevelopmentPlan
from app.models.profile import AgeGroup, Profile
from app.prompts import development_plan as prompt
from app.schemas.development_plan import DevelopmentPlanResponse
from app.services import assessment_shared, llm_client
from app.services.development_plan_context import (
    GenerationInput,
    build_generation_input,
)
from app.services.development_plan_validation import skeleton_problems, stage_problems

logger = logging.getLogger(__name__)

CACHE_TTL = 60 * 60 * 24  # 24h
_MAX_ATTEMPTS = 2  # 1 initial + 1 corrective retry
# Expand stages 2-at-a-time: fast enough to stay under nginx/read timeouts,
# light enough (~10k tokens in flight) to stay under a Tier-1 30k TPM cap.
_STAGE_CONCURRENCY = 2

_AI_UNAVAILABLE = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="ИИ временно недоступен, попробуй ещё раз",
)


def _cache_key(assessment_id: uuid.UUID, program_id: uuid.UUID) -> str:
    return f"{assessment_shared.DEVELOPMENT_PLAN_CACHE_KEY_PREFIX}:{assessment_id}:{program_id}"


async def _generate_skeleton(gi: GenerationInput) -> dict | None:
    messages = prompt.build_skeleton_messages(gi)
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            raw = await llm_client.complete_json(
                messages,
                prompt.SKELETON_SCHEMA,
                "devplan_skeleton",
                timeout=settings.LLM_DEVPLAN_TIMEOUT,
                max_tokens=settings.LLM_DEVPLAN_SKELETON_MAX_TOKENS,
                model=settings.LLM_DEVPLAN_MODEL,
            )
        except llm_client.LLMError as exc:
            logger.warning("devplan skeleton failed: %s", exc)
            return None
        problems = skeleton_problems(raw, grade=gi.grade, is_foreign=gi.is_foreign)
        if not problems:
            return raw
        logger.warning(
            "devplan skeleton invalid (attempt %s/%s): %s",
            attempt, _MAX_ATTEMPTS, "; ".join(problems),
        )
        messages = [*messages, prompt.SKELETON_RETRY_HINT]
    return None


async def _expand_stage(gi: GenerationInput, stage: dict) -> dict | None:
    messages = prompt.build_stage_messages(gi, stage)
    tracks_by_title = {t["title"]: t["track"] for t in stage["tasks"]}
    slot = stage.get("slot")
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            raw = await llm_client.complete_json(
                messages,
                prompt.STAGE_SCHEMA,
                "devplan_stage",
                timeout=settings.LLM_DEVPLAN_TIMEOUT,
                max_tokens=settings.LLM_DEVPLAN_STAGE_MAX_TOKENS,
                model=settings.LLM_DEVPLAN_MODEL,
            )
        except llm_client.LLMError as exc:
            logger.warning("devplan stage '%s' failed: %s", slot, exc)
            return None
        hard, soft = stage_problems(raw, tracks_by_title=tracks_by_title)
        if soft:
            logger.info("devplan stage '%s' soft notes: %s", slot, "; ".join(soft))
        if not hard:
            return raw
        logger.warning(
            "devplan stage '%s' invalid (attempt %s/%s): %s",
            slot, attempt, _MAX_ATTEMPTS, "; ".join(hard),
        )
        messages = [*messages, prompt.STAGE_RETRY_HINT]
    return None


def _merge_steps(stage: dict, expanded: dict) -> dict:
    """Staple phase-2 steps[] onto phase-1 tasks, matched by title."""
    steps_by_title = {t["title"]: t.get("steps", []) for t in expanded.get("tasks", [])}
    for task in stage["tasks"]:
        task["steps"] = steps_by_title.get(task["title"], [])
    return stage


async def _load_access(
    assessment_id: uuid.UUID, program_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> tuple[Assessment, Profile]:
    row = (
        await db.execute(
            select(Assessment, Profile)
            .join(Profile, Assessment.profile_id == Profile.id)
            .where(Assessment.id == assessment_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    assessment, profile = row
    if profile.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if profile.age_group != AgeGroup.senior:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="План развития доступен только для 9–11 классов",
        )
    return assessment, profile


async def generate_development_plan(
    assessment_id: uuid.UUID,
    program_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> DevelopmentPlanResponse:
    if not settings.DEVELOPMENT_PLAN_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not llm_client.is_enabled():
        raise _AI_UNAVAILABLE

    assessment, _profile = await _load_access(assessment_id, program_id, user_id, db)

    redis = assessment_shared.get_redis()
    key = _cache_key(assessment_id, program_id)
    cached = await redis.get(key)
    if cached:
        return DevelopmentPlanResponse.model_validate(json.loads(cached))

    gi = await build_generation_input(assessment_id, program_id, db)
    if gi is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Недостаточно данных для плана — пройди тест и выбери программу",
        )

    skeleton = await _generate_skeleton(gi)
    if skeleton is None:
        raise _AI_UNAVAILABLE

    sem = asyncio.Semaphore(_STAGE_CONCURRENCY)

    async def _bounded(stage: dict) -> dict | None:
        async with sem:
            return await _expand_stage(gi, stage)

    expanded = await asyncio.gather(*(_bounded(s) for s in skeleton["stages"]))
    if any(e is None for e in expanded):
        raise _AI_UNAVAILABLE

    stages = [_merge_steps(s, e) for s, e in zip(skeleton["stages"], expanded)]
    if not any(
        a.get("kind") == "repeat"
        for st in stages for t in st["tasks"] for s in t["steps"] for a in s["actions"]
    ):
        logger.warning("devplan %s/%s: no repeat action anywhere in the plan", assessment_id, program_id)

    try:
        response = DevelopmentPlanResponse.model_validate(
            {
                "id": uuid.uuid4(),
                "assessment_id": assessment_id,
                "program_id": program_id,
                "direction_slug": gi.direction_slug,
                "direction_name": gi.direction_name,
                "is_foreign": gi.is_foreign,
                "target": skeleton["target"],
                "about_you": skeleton["about_you"],
                "stages": stages,
                "admission_facts": gi.admission_facts,
            }
        )
    except ValidationError as exc:
        logger.warning("devplan assembly failed validation: %s", exc)
        raise _AI_UNAVAILABLE

    plan = await _upsert(assessment_id, program_id, gi, response, db)
    assessment.selected_direction_slug = gi.direction_slug
    await db.commit()
    await db.refresh(plan)

    out = DevelopmentPlanResponse.model_validate(plan)
    await assessment_shared.safe_redis_delete(redis, key)
    try:
        await redis.setex(key, CACHE_TTL, out.model_dump_json())
    except aioredis.RedisError:
        logger.warning("devplan cache write failed", exc_info=True)
    return out


async def _upsert(
    assessment_id: uuid.UUID,
    program_id: uuid.UUID,
    gi: GenerationInput,
    response: DevelopmentPlanResponse,
    db: AsyncSession,
) -> DevelopmentPlan:
    existing = (
        await db.execute(
            select(DevelopmentPlan).where(
                DevelopmentPlan.assessment_id == assessment_id,
                DevelopmentPlan.program_id == program_id,
            )
        )
    ).scalar_one_or_none()
    plan = existing or DevelopmentPlan(
        assessment_id=assessment_id, program_id=program_id
    )
    if existing is None:
        db.add(plan)

    plan.direction_slug = gi.direction_slug
    plan.direction_name = gi.direction_name
    plan.is_foreign = gi.is_foreign
    plan.target = response.target.model_dump()
    plan.about_you = response.about_you.model_dump()
    plan.stages = [s.model_dump() for s in response.stages]
    # `skills` / `subjects` DB columns are legacy — no longer part of the plan.
    plan.skills = []
    plan.subjects = []
    plan.admission_facts = response.admission_facts.model_dump(mode="json")
    return plan


async def get_development_plan(
    assessment_id: uuid.UUID,
    program_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> DevelopmentPlanResponse | None:
    await _load_access(assessment_id, program_id, user_id, db)

    redis = assessment_shared.get_redis()
    key = _cache_key(assessment_id, program_id)
    cached = await redis.get(key)
    if cached:
        return DevelopmentPlanResponse.model_validate(json.loads(cached))

    plan = (
        await db.execute(
            select(DevelopmentPlan).where(
                DevelopmentPlan.assessment_id == assessment_id,
                DevelopmentPlan.program_id == program_id,
            )
        )
    ).scalar_one_or_none()
    if plan is None:
        return None

    out = DevelopmentPlanResponse.model_validate(plan)
    try:
        await redis.setex(key, CACHE_TTL, out.model_dump_json())
    except aioredis.RedisError:
        logger.warning("devplan cache write failed", exc_info=True)
    return out
