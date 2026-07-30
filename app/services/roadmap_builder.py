import logging
import uuid
from dataclasses import dataclass

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.assessment import Assessment
from app.models.direction_roadmap import DirectionRoadmap
from app.models.profile import AgeGroup, Profile
from app.prompts import direction_roadmap as direction_prompt
from app.schemas.roadmap import (
    DirectionRoadmapResponse,
    GrowthFocus,
    ProfessionOption,
    SubjectPriority,
    UniversityRequirement,
)
from app.schemas.student_context import StudentContext
from app.services import direction_service, llm_client, result_service
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


class _SubjectNote(BaseModel):
    """Raw LLM output for one subject — no weight (that's Direction.subjects_required's,
    attached in _subjects_now_for, not something the model should invent)."""

    subject: str
    note: str


@dataclass
class _DirectionPlan:
    """The LLM's personalization layer, validated. Real facts (which
    professions exist, subject weights, university requirements) are NOT
    part of this — they're attached from the database in _upsert_direction_roadmap."""

    profession_options: list[ProfessionOption]
    subjects_now: list[_SubjectNote]
    starter_actions: list[str]
    growth_focus: GrowthFocus
    skills_to_build: list[str]


def direction_cache_key(assessment_id: uuid.UUID, slug: str) -> str:
    return f"droadmap:{assessment_id}:{slug}"


_MIN_PROFESSION_OPTIONS = 1
_MAX_PROFESSION_OPTIONS = 3
_MIN_STARTER_ACTIONS = 2
_MAX_STARTER_ACTIONS = 3


def _valid_plan(plan: _DirectionPlan, direction) -> bool:
    """Structure guard: profession_options are real (from Direction.professions,
    no duplicates, 1-3 of them), subjects_now covers exactly the direction's
    required subjects, starter_actions is a short concrete list."""
    professions = set(direction.professions or [])
    titles = [option.title for option in plan.profession_options]
    if not (_MIN_PROFESSION_OPTIONS <= len(titles) <= _MAX_PROFESSION_OPTIONS):
        return False
    if len(set(titles)) != len(titles):
        return False
    if any(title not in professions for title in titles):
        return False

    required_subjects = set((direction.subjects_required or {}).keys())
    plan_subjects = {note.subject for note in plan.subjects_now}
    if plan_subjects != required_subjects:
        return False

    if not (_MIN_STARTER_ACTIONS <= len(plan.starter_actions) <= _MAX_STARTER_ACTIONS):
        return False

    return True


async def _require_direction_roadmap_access(
    assessment_id: uuid.UUID, slug: str, db: AsyncSession
) -> tuple[Assessment, object, str]:
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

    confirmed = assessment.selected_direction_slug
    if confirmed is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сначала выберите это направление в тесте",
        )

    # Gap Analysis passes the URL-filter slug which may differ from the confirmed
    # leaf slug — always build the roadmap for what the user actually confirmed.
    if confirmed != slug:
        logger.info(
            "Roadmap requested for %r but assessment %s confirmed %r — using confirmed slug",
            slug, assessment_id, confirmed,
        )
        slug = confirmed

    direction = await direction_service.get_direction_by_slug(slug, db)
    if direction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Direction not found")

    return assessment, direction, slug


_MAX_PLAN_ATTEMPTS = 2


async def _generate_plan(context: StudentContext, direction) -> _DirectionPlan | None:
    """Up to _MAX_PLAN_ATTEMPTS total tries. Both failure modes — a malformed/
    unparseable response (LLMError/ValidationError/TypeError) and a structurally
    invalid one (_valid_plan) — share the same attempt budget and both get
    the same corrective RETRY_HINT nudge appended before the next try."""
    messages = direction_prompt.build_messages(context, direction)

    for attempt in range(1, _MAX_PLAN_ATTEMPTS + 1):
        is_last_attempt = attempt == _MAX_PLAN_ATTEMPTS
        try:
            raw = await llm_client.complete_json(
                messages,
                direction_prompt.DIRECTION_ROADMAP_SCHEMA,
                "direction_roadmap",
                timeout=settings.LLM_ROADMAP_TIMEOUT,
                max_tokens=settings.LLM_ROADMAP_MAX_TOKENS,
            )
            plan = _DirectionPlan(
                profession_options=[
                    ProfessionOption.model_validate(p) for p in raw.get("profession_options", [])
                ],
                subjects_now=[
                    _SubjectNote.model_validate(s) for s in raw.get("subjects_now", [])
                ],
                starter_actions=list(raw.get("starter_actions", [])),
                growth_focus=GrowthFocus.model_validate(raw.get("growth_focus", {})),
                skills_to_build=list(raw.get("skills_to_build", [])),
            )
        except (llm_client.LLMError, ValidationError, TypeError) as exc:
            logger.warning(
                "Direction roadmap generation failed (attempt %s/%s): %s",
                attempt, _MAX_PLAN_ATTEMPTS, exc,
            )
            if is_last_attempt:
                return None
            messages = [*messages, direction_prompt.RETRY_HINT]
            continue

        if _valid_plan(plan, direction):
            return plan

        logger.warning(
            "Direction roadmap failed invariant check (attempt %s/%s)",
            attempt, _MAX_PLAN_ATTEMPTS,
        )
        if is_last_attempt:
            return None
        messages = [*messages, direction_prompt.RETRY_HINT]

    return None


async def generate_direction_roadmap(
    assessment_id: uuid.UUID, slug: str, db: AsyncSession
) -> DirectionRoadmapResponse:
    if not llm_client.is_enabled():
        raise _AI_UNAVAILABLE

    # Access check normalises slug to the confirmed direction when they differ.
    assessment, direction, effective_slug = await _require_direction_roadmap_access(
        assessment_id, slug, db
    )

    redis = _get_redis()
    key = direction_cache_key(assessment_id, effective_slug)
    cached = await redis.get(key)
    if cached:
        return DirectionRoadmapResponse.model_validate_json(cached)

    context = await build_student_context(assessment_id, db, direction_slug=effective_slug)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    plan = await _generate_plan(context, direction)
    if plan is None:
        raise _AI_UNAVAILABLE

    roadmap = await _upsert_direction_roadmap(assessment_id, effective_slug, direction, plan, db)
    assessment.selected_direction_slug = effective_slug
    await db.commit()
    await db.refresh(roadmap)

    response = DirectionRoadmapResponse.model_validate(roadmap)
    await redis.setex(key, CACHE_TTL, response.model_dump_json())
    return response


def _starter_actions_for(direction, plan: _DirectionPlan) -> list[str]:
    """Direction.first_steps (curated, real) wins when authored; otherwise the
    LLM's on-the-fly fallback, written in the same concrete style (see the
    prompt's style-anchor examples)."""
    curated = list(direction.first_steps or [])
    return curated if curated else list(plan.starter_actions)


def _subjects_now_for(direction, plan: _DirectionPlan) -> list[SubjectPriority]:
    """Real subject weights from Direction.subjects_required, personalized
    notes from the LLM — weight ordering is never the model's call."""
    weights: dict[str, int] = direction.subjects_required or {}
    notes = {note.subject: note.note for note in plan.subjects_now}
    return sorted(
        (
            SubjectPriority(subject=subject, weight=weight, note=notes.get(subject, ""))
            for subject, weight in weights.items()
        ),
        key=lambda item: item.weight,
        reverse=True,
    )


_UNIVERSITY_REQUIREMENTS_LIMIT = 3


async def _university_requirements_for(
    direction_slug: str, db: AsyncSession
) -> list[UniversityRequirement]:
    """Real admission facts for a few real programs matching this direction —
    entirely backend-populated (reuses result_service.recommended_programs_for,
    the same real Program/University rows /results shows), no LLM involved.
    No city filter here (unlike /results): the goal is showing what admission
    for this direction generally requires, not just what's nearby."""
    programs = await result_service.recommended_programs_for(direction_slug, db, city=None)
    items = []
    for program in programs[:_UNIVERSITY_REQUIREMENTS_LIMIT]:
        requirements = program.requirements or {}
        items.append(
            UniversityRequirement(
                program_name=program.name,
                university_name=program.university.name,
                city=program.university.city,
                exams=list(requirements.get("exams", [])),
                admission_requirements=list(requirements.get("admission_requirements", [])),
                admission_summary=requirements.get("admission_summary", ""),
            )
        )
    return items


async def _upsert_direction_roadmap(
    assessment_id: uuid.UUID,
    slug: str,
    direction,
    plan: _DirectionPlan,
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
            direction_name=direction.name,
        )
        db.add(roadmap)
    else:
        roadmap = existing

    roadmap.direction_name = direction.name
    roadmap.profession_options = [p.model_dump() for p in plan.profession_options]
    roadmap.subjects_now = [s.model_dump() for s in _subjects_now_for(direction, plan)]
    roadmap.starter_actions = _starter_actions_for(direction, plan)
    roadmap.growth_focus = plan.growth_focus.model_dump()
    roadmap.skills_to_build = plan.skills_to_build
    roadmap.university_requirements = [
        u.model_dump() for u in await _university_requirements_for(slug, db)
    ]
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
