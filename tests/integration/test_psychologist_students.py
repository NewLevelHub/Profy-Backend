"""GET /api/v1/psychologist/students — assigned students only (PRO-327).
Detail + full report also covered here."""

import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

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
