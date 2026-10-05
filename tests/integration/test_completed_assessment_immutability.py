"""PROFY-001: completed diagnostics are immutable through answer APIs.

Retaking the full diagnostic creates a new Assessment.  A stale browser tab
must not reopen the old row or delete its generated/reviewed report, including
when it sends an empty autosave payload.
"""

import uuid
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import (
    assessment_service,
    assessment_shared,
    auth_service,
    motivation_service,
    question_pair_service,
)


async def _make_completed_assessment(
    db_session: AsyncSession,
) -> tuple[Assessment, Profile, AnalysisResult, User]:
    user = User(
        email=f"{uuid.uuid4()}@example.test",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    profile = Profile(
        user_id=user.id,
        name="Тест",
        age=16,
        grade=10,
        city="Алматы",
        country="Казахстан",
        language="ru",
        age_group=AgeGroup.senior,
    )
    db_session.add(profile)
    await db_session.flush()

    completed_at = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
    assessment = Assessment(
        profile_id=profile.id,
        goal=AssessmentGoal.explore,
        status=AssessmentStatus.completed,
        completed_at=completed_at,
        secondary_goals=[AssessmentGoal.profession],
        goal_changed_count=2,
    )
    db_session.add(assessment)
    await db_session.flush()

    report = AnalysisResult(
        assessment_id=assessment.id,
        summary="published report",
        profile={},
        code=[],
        meta={"differentiation": 0.0, "consistency": "high", "aversion": {}},
        careers=[],
        strengths=[],
        weaknesses=[],
        development_plan={"reinforce": [], "compensate": []},
        big_five={},
        thinking_style={
            "creative_think": 0.0,
            "systematic": 0.0,
            "strategic": 0.0,
            "practical": 0.0,
        },
        personality_highlights=[],
        motivation={},
        motivation_top=[],
        motivation_highlights=[],
        personality_profile={},
        personality_notes={},
    )
    db_session.add(report)
    await db_session.flush()
    return assessment, profile, report, user


@pytest.mark.parametrize(
    "entrypoint",
    ["ordinary_answers", "pair_answers", "motivation_answers"],
)
async def test_completed_assessment_rejects_answers_without_changing_report(
    db_session: AsyncSession, entrypoint: str
) -> None:
    assessment, profile, report, _user = await _make_completed_assessment(db_session)
    original_completed_at = assessment.completed_at
    cache_keys = assessment_shared.report_cache_keys(assessment.id)
    redis = assessment_shared.get_redis()
    for cache_key in cache_keys:
        await redis.set(cache_key, "published")

    with pytest.raises(AppError) as exc_info:
        if entrypoint == "ordinary_answers":
            await assessment_service.submit_answers(
                assessment.id, [], profile.id, db_session
            )
        elif entrypoint == "pair_answers":
            await question_pair_service.submit_pair_answers(
                assessment.id, [], profile.id, db_session
            )
        else:
            await motivation_service.submit_motivation_answers(
                assessment.id, [], profile.id, db_session
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "assessment_already_completed"

    await db_session.refresh(assessment)
    assert assessment.status == AssessmentStatus.completed
    assert assessment.completed_at == original_completed_at
    assert assessment.goal_changed_count == 2
    assert assessment.secondary_goals == [AssessmentGoal.profession]

    stored_report = (
        await db_session.execute(
            select(AnalysisResult).where(AnalysisResult.id == report.id)
        )
    ).scalar_one_or_none()
    assert stored_report is not None
    assert stored_report.summary == "published report"
    for cache_key in cache_keys:
        assert await redis.get(cache_key) == "published"


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("answers", {"answers": []}),
        ("pair-answers", {"answers": []}),
        ("motivation-answers", {"answers": []}),
    ],
)
async def test_completed_assessment_answer_apis_return_stable_conflict(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    path: str,
    payload: dict,
) -> None:
    assessment, _profile, _report, user = await _make_completed_assessment(
        db_session
    )
    headers = {
        "Authorization": f"Bearer {auth_service.create_jwt_token(user.id)}"
    }

    response = await client.post(
        f"/api/v1/assessment/{assessment.id}/{path}",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["error_code"] == "assessment_already_completed"
