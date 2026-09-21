"""PRO-338 post-Ф4.1 follow-up: psychologist assigns Belbin/АСТУР, student
discovers it via GET .../extended-blocks instead of a hand-delivered link."""
import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.astur_run import AsturRun
from app.models.belbin_run import BelbinRun
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import auth_service


async def _make_assessment_for(db: AsyncSession, owner: User) -> Assessment:
    profile = Profile(
        user_id=owner.id, name="Т", age=16, grade=10, city="Алматы",
        country="Казахстан", language="ru", age_group=AgeGroup.senior,
    )
    db.add(profile)
    await db.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()
    return assessment


async def _assign_api(client: httpx.AsyncClient, admin_headers: dict, psychologist_id: uuid.UUID, student_id: uuid.UUID) -> None:
    response = await client.post(
        "/api/v1/admin/psychologist-assignments",
        json={"psychologist_id": str(psychologist_id), "student_id": str(student_id)},
        headers=admin_headers,
    )
    assert response.status_code == 201


async def test_psychologist_assigns_a_block_and_student_sees_it(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await _assign_api(client, admin_headers, psychologist_user.id, test_user.id)
    assessment = await _make_assessment_for(db_session, test_user)

    resp = await client.post(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{assessment.id}/extended-blocks",
        json={"block": "belbin"},
        headers=psychologist_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["block"] == "belbin"
    assert resp.json()["completed"] is False

    student_headers = {"Authorization": f"Bearer {auth_service.create_jwt_token(test_user.id)}"}
    resp2 = await client.get(
        f"/api/v1/assessment/{assessment.id}/extended-blocks",
        headers=student_headers,
    )
    assert resp2.status_code == 200, resp2.text
    assignments = resp2.json()["assignments"]
    assert len(assignments) == 1
    assert assignments[0]["block"] == "belbin"
    assert assignments[0]["completed"] is False


async def test_assigning_twice_is_idempotent(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await _assign_api(client, admin_headers, psychologist_user.id, test_user.id)
    assessment = await _make_assessment_for(db_session, test_user)

    for _ in range(2):
        resp = await client.post(
            f"/api/v1/psychologist/students/{test_user.id}/assessments/{assessment.id}/extended-blocks",
            json={"block": "astur"},
            headers=psychologist_headers,
        )
        assert resp.status_code == 201

    student_headers = {"Authorization": f"Bearer {auth_service.create_jwt_token(test_user.id)}"}
    resp = await client.get(
        f"/api/v1/assessment/{assessment.id}/extended-blocks", headers=student_headers,
    )
    assert len(resp.json()["assignments"]) == 1  # not 2 rows


async def test_completed_flag_reflects_a_real_belbin_run(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await _assign_api(client, admin_headers, psychologist_user.id, test_user.id)
    assessment = await _make_assessment_for(db_session, test_user)
    await client.post(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{assessment.id}/extended-blocks",
        json={"block": "belbin"},
        headers=psychologist_headers,
    )
    db_session.add(BelbinRun(
        assessment_id=assessment.id, user_id=test_user.id,
        allocations=[], role_totals={"implementer": 70},
    ))
    await db_session.flush()

    student_headers = {"Authorization": f"Bearer {auth_service.create_jwt_token(test_user.id)}"}
    resp = await client.get(
        f"/api/v1/assessment/{assessment.id}/extended-blocks", headers=student_headers,
    )
    assert resp.json()["assignments"][0]["completed"] is True


async def test_astur_completed_requires_all_scored_subtests_not_just_any_row(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await _assign_api(client, admin_headers, psychologist_user.id, test_user.id)
    assessment = await _make_assessment_for(db_session, test_user)
    await client.post(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{assessment.id}/extended-blocks",
        json={"block": "astur"},
        headers=psychologist_headers,
    )
    # Only 1 of 6 scored subtests answered — a row exists but it's not done.
    db_session.add(AsturRun(
        assessment_id=assessment.id, user_id=test_user.id,
        answers={"awareness": {"1": "x"}},
    ))
    await db_session.flush()

    student_headers = {"Authorization": f"Bearer {auth_service.create_jwt_token(test_user.id)}"}
    resp = await client.get(
        f"/api/v1/assessment/{assessment.id}/extended-blocks", headers=student_headers,
    )
    assert resp.json()["assignments"][0]["completed"] is False


async def test_a_different_student_cannot_see_another_students_assignments(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await _assign_api(client, admin_headers, psychologist_user.id, test_user.id)
    assessment = await _make_assessment_for(db_session, test_user)
    await client.post(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{assessment.id}/extended-blocks",
        json={"block": "belbin"},
        headers=psychologist_headers,
    )

    other = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x", is_active=True, is_verified=True)
    db_session.add(other)
    await db_session.flush()
    other_headers = {"Authorization": f"Bearer {auth_service.create_jwt_token(other.id)}"}

    resp = await client.get(
        f"/api/v1/assessment/{assessment.id}/extended-blocks", headers=other_headers,
    )
    assert resp.status_code == 403
