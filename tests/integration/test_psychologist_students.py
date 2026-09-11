"""GET /api/v1/psychologist/students — a psychologist sees every student
(PRO-321 rework: no assignment step). Detail + full report also covered here.
"""

import uuid

import httpx

from app.models.user import User, UserRole
from app.services import auth_service


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


async def test_list_returns_every_student(
    client: httpx.AsyncClient,
    psychologist_headers: dict[str, str],
    test_user: User,
    db_session,
) -> None:
    other = User(
        email=f"{uuid.uuid4()}@example.com",
        hashed_password=auth_service.hash_password("Testpass123!"),
        is_active=True,
        is_verified=True,
        role=UserRole.student,
    )
    db_session.add(other)
    await db_session.flush()

    response = await client.get(
        "/api/v1/psychologist/students", headers=psychologist_headers
    )
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()}
    assert str(test_user.id) in ids
    assert str(other.id) in ids


async def test_list_excludes_non_students(
    client: httpx.AsyncClient,
    psychologist_headers: dict[str, str],
    admin_user: User,
    psychologist_user: User,
) -> None:
    response = await client.get(
        "/api/v1/psychologist/students", headers=psychologist_headers
    )
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()}
    assert str(admin_user.id) not in ids
    assert str(psychologist_user.id) not in ids


async def test_get_any_student_detail(
    client: httpx.AsyncClient,
    psychologist_headers: dict[str, str],
    test_user: User,
) -> None:
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


async def test_get_non_student_returns_404(
    client: httpx.AsyncClient,
    psychologist_headers: dict[str, str],
    admin_user: User,
) -> None:
    response = await client.get(
        f"/api/v1/psychologist/students/{admin_user.id}",
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


async def test_get_student_report_unknown_assessment_404(
    client: httpx.AsyncClient,
    psychologist_headers: dict[str, str],
    test_user: User,
) -> None:
    response = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}/result/{uuid.uuid4()}",
        headers=psychologist_headers,
    )
    assert response.status_code == 404
