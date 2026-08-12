"""Retake acceptance matrix: each of the 4 real submit-answers entrypoints
(ordinary Likert answers, question pairs, Harter motivation pairs, senior
motivation triplets) must — through the shared `assessment_shared.
invalidate_retake()` — delete the *entire* set of stale, assessment-derived
artifacts: the report row + its cache, the direction-fit inquiry/roadmap
rows + their caches, and the goal roadmap row + all its cached variants.

tests/integration/test_report_cache_resilience.py already pins the report
*cache key* being cleared for all 4 entrypoints, and tests/integration/
test_goal_roadmap_retake_invalidation.py already pins invalidate_goal_roadmap
in isolation. Neither exercises all 4 real entrypoints against the *full*
artifact set (AnalysisResult row, DirectionInquiry, DirectionRoadmap, Roadmap
+ every cache key) at once — this file closes that gap.
"""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.direction_inquiry import DirectionInquiry
from app.models.direction_roadmap import DirectionRoadmap
from app.models.profile import AgeGroup, Profile
from app.models.roadmap import Roadmap
from app.models.user import User
from app.services import (
    assessment_service,
    assessment_shared,
    motivation_pair_service,
    motivation_service,
    question_pair_service,
)

_DIRECTION_SLUG = "test-swe"


async def _make_assessment(db_session: AsyncSession) -> Assessment:
    user = User(
        email=f"{uuid.uuid4()}@example.test", hashed_password="x", is_active=True, is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    profile = Profile(
        user_id=user.id, name="Тест", age=16, grade=10,
        city="Алматы", country="Казахстан", language="ru", age_group=AgeGroup.senior,
    )
    db_session.add(profile)
    await db_session.flush()

    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    assessment.status = AssessmentStatus.completed
    assessment.selected_direction_slug = _DIRECTION_SLUG
    db_session.add(assessment)
    await db_session.flush()
    return assessment


def _minimal_analysis_kwargs(assessment_id: uuid.UUID) -> dict:
    return dict(
        assessment_id=assessment_id,
        summary="s",
        profile={},
        code=[],
        meta={"differentiation": 0.0, "consistency": "high", "aversion": {}},
        careers=[],
        strengths=[],
        weaknesses=[],
        development_plan={"reinforce": [], "compensate": []},
        big_five={},
        thinking_style={"creative_think": 0.0, "systematic": 0.0, "strategic": 0.0, "practical": 0.0},
        personality_highlights=[],
        motivation={},
        motivation_top=[],
        motivation_highlights=[],
        personality_profile={},
        personality_notes={},
    )


async def _seed_stale_artifacts(assessment: Assessment, db_session: AsyncSession) -> dict[str, str]:
    """Plants one row per artifact type + one Redis key per cache type —
    everything invalidate_retake is supposed to remove."""
    db_session.add(AnalysisResult(**_minimal_analysis_kwargs(assessment.id)))
    db_session.add(DirectionInquiry(
        assessment_id=assessment.id, direction_slug=_DIRECTION_SLUG,
        questions=[], answers=[], readiness="ready", fit_summary="x", note="x",
    ))
    db_session.add(DirectionRoadmap(
        assessment_id=assessment.id, direction_slug=_DIRECTION_SLUG, direction_name="SWE",
    ))
    db_session.add(Roadmap(assessment_id=assessment.id, goal="explore", milestones=[]))
    await db_session.flush()

    redis = assessment_shared.get_redis()
    keys = {
        "report": assessment_shared.report_cache_key(assessment.id),
        "droadmap": f"droadmap:{assessment.id}:{_DIRECTION_SLUG}",
        "dq": f"dq:{assessment.id}:{_DIRECTION_SLUG}",
        "goal_roadmap": f"roadmap:{assessment.id}:none",
    }
    for key in keys.values():
        await redis.set(key, "stale")
    return keys


async def _assert_everything_gone(
    assessment: Assessment, keys: dict[str, str], db_session: AsyncSession
) -> None:
    for kind, model in (
        ("report", AnalysisResult),
        ("inquiry", DirectionInquiry),
        ("direction_roadmap", DirectionRoadmap),
        ("goal_roadmap_row", Roadmap),
    ):
        row = (
            await db_session.execute(select(model).where(model.assessment_id == assessment.id))
        ).scalar_one_or_none()
        assert row is None, f"{kind} row survived retake"

    redis = assessment_shared.get_redis()
    for kind, key in keys.items():
        assert await redis.get(key) is None, f"{kind} cache key survived retake"

    await db_session.refresh(assessment)
    assert assessment.status == AssessmentStatus.in_progress
    assert assessment.selected_direction_slug is None


async def test_ordinary_answers_retake_clears_every_artifact(db_session: AsyncSession) -> None:
    assessment = await _make_assessment(db_session)
    profile = (await db_session.execute(select(Profile).where(Profile.id == assessment.profile_id))).scalar_one()
    keys = await _seed_stale_artifacts(assessment, db_session)

    await assessment_service.submit_answers(assessment.id, [], profile.id, db_session)

    await _assert_everything_gone(assessment, keys, db_session)


async def test_question_pairs_retake_clears_every_artifact(db_session: AsyncSession) -> None:
    assessment = await _make_assessment(db_session)
    profile = (await db_session.execute(select(Profile).where(Profile.id == assessment.profile_id))).scalar_one()
    keys = await _seed_stale_artifacts(assessment, db_session)

    await question_pair_service.submit_pair_answers(assessment.id, [], profile.id, db_session)

    await _assert_everything_gone(assessment, keys, db_session)


async def test_harter_motivation_pairs_retake_clears_every_artifact(db_session: AsyncSession) -> None:
    assessment = await _make_assessment(db_session)
    profile = (await db_session.execute(select(Profile).where(Profile.id == assessment.profile_id))).scalar_one()
    keys = await _seed_stale_artifacts(assessment, db_session)

    await motivation_pair_service.submit_pair_answers(assessment.id, [], profile.id, db_session)

    await _assert_everything_gone(assessment, keys, db_session)


async def test_senior_motivation_triplets_retake_clears_every_artifact(db_session: AsyncSession) -> None:
    assessment = await _make_assessment(db_session)
    profile = (await db_session.execute(select(Profile).where(Profile.id == assessment.profile_id))).scalar_one()
    keys = await _seed_stale_artifacts(assessment, db_session)

    await motivation_service.submit_motivation_answers(assessment.id, [], profile.id, db_session)

    await _assert_everything_gone(assessment, keys, db_session)
