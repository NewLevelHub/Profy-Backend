import logging
import uuid
from typing import Literal, Optional

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.i18n.catalog import tr
from app.models.assessment import AssessmentGoal
from app.models.goal_overlay import GoalOverlay
from app.models.profile import AgeGroup
from app.services import assessment_shared

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def invalidate_goal_overlay_cache(assessment_id: uuid.UUID, db: AsyncSession) -> None:
    """Nothing builds goal overlays anymore (the `goal-context` endpoint was
    removed in PRO-425) — this only clears rows/keys left over from before."""
    redis = _get_redis()
    try:
        # Delete from DB
        await db.execute(GoalOverlay.__table__.delete().where(GoalOverlay.assessment_id == assessment_id))
        # Scan and delete keys matching the assessment
        pattern = f"goal_context:{assessment_id}:*"
        keys = []
        async for key in redis.scan_iter(match=pattern):
            keys.append(key)
        if keys:
            await redis.delete(*keys)
            logger.info("Invalidated goal overlay caches: %s", keys)
    except Exception as exc:
        logger.warning("Failed to invalidate goal overlay caches for %s: %s", assessment_id, exc)


_SCENARIO_BY_GOAL: dict[AssessmentGoal, Literal["A", "B", "C"]] = {
    AssessmentGoal.explore: "A",
    AssessmentGoal.profession: "B",
    AssessmentGoal.university: "C",
}

def _middle_university_downgrade_note() -> str:
    return tr("goal_overlay")["middle_university_downgrade_note"]


def _get_effective_goal_and_scenario(
    age_group: AgeGroup, primary_goal: AssessmentGoal
) -> tuple[AssessmentGoal, Literal["A", "B", "C"], bool, Optional[str]]:
    """Display-layer wrapper around `assessment_shared.get_effective_goal` — the
    scenario letter and "redirected" banner text shown here must always agree
    with what roadmap/report generation actually runs under, so the goal
    mapping itself lives in that one shared function, not here."""
    effective_goal = assessment_shared.get_effective_goal(age_group, primary_goal)
    scenario = _SCENARIO_BY_GOAL[effective_goal]

    if age_group == AgeGroup.junior:
        redirected = primary_goal != AssessmentGoal.explore
        return effective_goal, scenario, redirected, None

    if age_group == AgeGroup.middle and primary_goal == AssessmentGoal.university:
        return effective_goal, scenario, True, _middle_university_downgrade_note()

    return effective_goal, scenario, False, None
