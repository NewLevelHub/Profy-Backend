import uuid
import pytest
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.profile import AgeGroup, Profile
from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.direction import Direction
from app.models.analysis_result import AnalysisResult
from app.models.goal_overlay import GoalOverlay
from app.services import auth_service


async def _create_test_student(
    db: AsyncSession, age_group: AgeGroup, email_prefix: str = "student"
) -> tuple[User, Profile, Assessment]:
    user = User(
        email=f"{email_prefix}-{uuid.uuid4()}@example.test",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.flush()

    age_map = {AgeGroup.junior: 9, AgeGroup.middle: 13, AgeGroup.senior: 17}
    profile = Profile(
        user_id=user.id,
        name="Тестовый Студент",
        age=age_map[age_group],
        grade=5,
        city="Алматы",
        country="Казахстан",
        language="ru",
        age_group=age_group,
    )
    db.add(profile)
    await db.flush()

    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()

    return user, profile, assessment


async def test_junior_cannot_select_career_goals(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    # 1. Setup Junior
    user, profile, assessment = await _create_test_student(db_session, AgeGroup.junior, "junior")
    await db_session.commit()

    # Get JWT token headers for test user
    token = auth_service.create_jwt_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Try setting goal to profession
    payload = {"goal": "profession", "secondary_goals": []}
    response = await client.patch(
        f"/api/v1/assessment/{assessment.id}/goal", json=payload, headers=headers
    )
    assert response.status_code == 400
    assert "Для младшей возрастной группы" in response.json()["detail"]

    # Try setting secondary goals to profession
    payload = {"goal": "explore", "secondary_goals": ["profession"]}
    response = await client.patch(
        f"/api/v1/assessment/{assessment.id}/goal", json=payload, headers=headers
    )
    assert response.status_code == 400


async def test_goal_change_limits(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    # 1. Setup Completed Senior
    user, profile, assessment = await _create_test_student(db_session, AgeGroup.senior, "senior")
    assessment.status = AssessmentStatus.completed
    await db_session.commit()

    token = auth_service.create_jwt_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Change 1 -> OK
    response = await client.patch(
        f"/api/v1/assessment/{assessment.id}/goal",
        json={"goal": "profession", "secondary_goals": []},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["goal_changed_count"] == 1

    # Change 2 -> OK
    response = await client.patch(
        f"/api/v1/assessment/{assessment.id}/goal",
        json={"goal": "university", "secondary_goals": []},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["goal_changed_count"] == 2

    # Change 3 -> OK
    response = await client.patch(
        f"/api/v1/assessment/{assessment.id}/goal",
        json={"goal": "explore", "secondary_goals": []},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["goal_changed_count"] == 3

    # Change 4 -> Fail
    response = await client.patch(
        f"/api/v1/assessment/{assessment.id}/goal",
        json={"goal": "profession", "secondary_goals": []},
        headers=headers,
    )
    assert response.status_code == 400
    assert "Достигнут лимит смены целей" in response.json()["detail"]


async def test_unsure_goal_interstitial_state(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    # 1. Setup Completed Senior with unsure goal
    user, profile, assessment = await _create_test_student(db_session, AgeGroup.senior, "unsure")
    assessment.goal = AssessmentGoal.unsure
    assessment.status = AssessmentStatus.completed
    await db_session.commit()

    token = auth_service.create_jwt_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Request goal context
    response = await client.get(
        f"/api/v1/result/{assessment.id}/goal-context", headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["needs_goal_selection"] is True
    assert set(data["suggested_goals"]) == {"explore", "profession", "university"}
    assert data["scenario"] is None


async def test_alignment_match_partial_bridge(
    client: httpx.AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    # Mock completeness assertion
    async def mock_assert(*args, **kwargs):
        return
    monkeypatch.setattr("app.services.report_service._assert_assessment_complete", mock_assert)

    # 1. Setup Senior with completed assessment & careers analysis result
    user, profile, assessment = await _create_test_student(db_session, AgeGroup.senior, "align")
    assessment.goal = AssessmentGoal.profession
    assessment.status = AssessmentStatus.completed
    
    # Pre-seed some directions
    dir_dev = Direction(name="Разработчик", slug="developer", holland_code="IRC")
    dir_eng = Direction(name="Инженер", slug="engineer", holland_code="RIS")
    dir_art = Direction(name="Художник", slug="artist", holland_code="AIR")
    db_session.add_all([dir_dev, dir_eng, dir_art])
    await db_session.flush()

    # Pre-seed analysis result where developer is top 1, artist is top 4, engineer is outside top 10
    analysis = AnalysisResult(
        assessment_id=assessment.id,
        summary="Test summary",
        strengths=["I", "R", "C"],
        weaknesses=["S", "E", "A"],
        careers=[
            {"slug": "developer", "name": "Разработчик", "holland_code": "IRC", "why": "..."}
        ] + [{"slug": f"other-{i}", "name": f"Other {i}", "holland_code": "IRC", "why": "..."} for i in range(2)] + [
            {"slug": "artist", "name": "Художник", "holland_code": "AIR", "why": "..."}
        ],
        profile={"I": 10.0, "R": 8.0, "C": 6.0},
    )
    db_session.add(analysis)
    await db_session.flush()

    assessment.selected_direction_slug = "developer"
    await db_session.commit()

    token = auth_service.create_jwt_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Request goal context with developer selected (Top 1 -> match)
    response = await client.get(
        f"/api/v1/result/{assessment.id}/goal-context", headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["alignment_block"]["target_selected"] is True
    assert data["alignment_block"]["alignment"] == "match"

    # Switch to artist (Top 4 -> partial)
    assessment.selected_direction_slug = "artist"
    await db_session.commit()
    # Invalidate overlay to force recalculation
    from app.services.goal_overlay_service import invalidate_goal_overlay_cache
    await invalidate_goal_overlay_cache(assessment.id, db_session)

    response = await client.get(
        f"/api/v1/result/{assessment.id}/goal-context", headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["alignment_block"]["alignment"] == "partial"

    # Switch to engineer (Not in careers -> bridge)
    assessment.selected_direction_slug = "engineer"
    await db_session.commit()
    await invalidate_goal_overlay_cache(assessment.id, db_session)

    response = await client.get(
        f"/api/v1/result/{assessment.id}/goal-context", headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["alignment_block"]["alignment"] == "bridge"
    # Verify adjacent directions contain Developer and Artist (sharing overlap in codes)
    assert len(data["alignment_block"]["adjacent_directions"]) > 0
