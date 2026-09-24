"""GET /api/v1/psychologist/students — assigned students only (PRO-327).
Detail + full report also covered here."""

import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.profile import AgeGroup, Profile
from app.models.user import User

from tests.integration.review_helpers import assign


async def test_list_students_requires_psychologist(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/psychologist/students", headers=auth_headers)
    assert response.status_code == 403


async def test_list_students_rejects_admin(
    client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/psychologist/students", headers=admin_headers)
    assert response.status_code == 403


async def test_list_students_empty_without_assignments(
    client: httpx.AsyncClient, psychologist_headers: dict[str, str]
) -> None:
    response = await client.get(
        "/api/v1/psychologist/students", headers=psychologist_headers
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_list_and_get_assigned_student(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await assign(db_session, psychologist_user, test_user)

    listed = await client.get(
        "/api/v1/psychologist/students", headers=psychologist_headers
    )
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 1
    assert items[0]["id"] == str(test_user.id)
    assert items[0]["email"] == test_user.email

    detail = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}",
        headers=psychologist_headers,
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == str(test_user.id)
    assert body["email"] == test_user.email
    assert "is_admin" not in body
    assert "role" not in body
    assert "assessments" in body


async def test_get_unassigned_student_returns_404(
    client: httpx.AsyncClient,
    psychologist_headers: dict[str, str],
    test_user: User,
) -> None:
    response = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}",
        headers=psychologist_headers,
    )
    assert response.status_code == 404


async def test_get_unknown_student_returns_404(
    client: httpx.AsyncClient, psychologist_headers: dict[str, str]
) -> None:
    response = await client.get(
        f"/api/v1/psychologist/students/{uuid.uuid4()}",
        headers=psychologist_headers,
    )
    assert response.status_code == 404


async def test_get_student_test_results_requires_assignment(
    client: httpx.AsyncClient,
    psychologist_headers: dict[str, str],
    test_user: User,
) -> None:
    # No assignment created — must 404 before the assessment lookup even runs.
    response = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{uuid.uuid4()}/test-results",
        headers=psychologist_headers,
    )
    assert response.status_code == 404


async def test_get_student_test_results_unknown_assessment_404(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await assign(db_session, psychologist_user, test_user)

    response = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{uuid.uuid4()}/test-results",
        headers=psychologist_headers,
    )
    assert response.status_code == 404


async def test_available_students_flags_completed_assessment(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    test_user: User,
) -> None:
    """PRO-402: claim CTA needs has_completed_assessment, not only pending review."""
    before = await client.get(
        "/api/v1/psychologist/students/available", headers=psychologist_headers
    )
    assert before.status_code == 200
    row = next(item for item in before.json() if item["id"] == str(test_user.id))
    assert row["has_completed_assessment"] is False
    assert row["has_pending_review"] is False

    profile = Profile(
        user_id=test_user.id,
        name="Test Student",
        age=16,
        grade=10,
        city="Алматы",
        country="Казахстан",
        language="ru",
        age_group=AgeGroup.senior,
    )
    db_session.add(profile)
    await db_session.flush()
    db_session.add(
        Assessment(
            profile_id=profile.id,
            goal=AssessmentGoal.explore,
            status=AssessmentStatus.completed,
        )
    )
    await db_session.commit()

    after = await client.get(
        "/api/v1/psychologist/students/available", headers=psychologist_headers
    )
    assert after.status_code == 200
    row = next(item for item in after.json() if item["id"] == str(test_user.id))
    assert row["has_completed_assessment"] is True
    assert row["has_pending_review"] is False


async def test_scope_available_excludes_already_claimed_student(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    """PRO-422: ?scope=available must not return students already claimed."""
    created = await client.post(
        "/api/v1/admin/psychologist-assignments",
        json={
            "psychologist_id": str(psychologist_user.id),
            "student_id": str(test_user.id),
        },
        headers=admin_headers,
    )
    assert created.status_code == 201

    mine = await client.get(
        "/api/v1/psychologist/students?scope=mine", headers=psychologist_headers
    )
    assert mine.status_code == 200
    assert any(item["id"] == str(test_user.id) for item in mine.json())

    for path in (
        "/api/v1/psychologist/students?scope=available",
        "/api/v1/psychologist/students/available",
    ):
        available = await client.get(path, headers=psychologist_headers)
        assert available.status_code == 200, path
        assert all(item["id"] != str(test_user.id) for item in available.json()), path
