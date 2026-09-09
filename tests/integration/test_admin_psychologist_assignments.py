"""POST/GET/DELETE /api/v1/admin/psychologist-assignments (PRO-326)."""

import uuid

import httpx

from app.models.user import User


async def test_create_assignment_requires_admin(
    client: httpx.AsyncClient, auth_headers: dict[str, str], psychologist_user: User, test_user: User
) -> None:
    response = await client.post(
        "/api/v1/admin/psychologist-assignments",
        json={"psychologist_id": str(psychologist_user.id), "student_id": str(test_user.id)},
        headers=auth_headers,
    )
    assert response.status_code == 403


async def test_create_assignment_rejects_psychologist_caller(
    client: httpx.AsyncClient,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    response = await client.post(
        "/api/v1/admin/psychologist-assignments",
        json={"psychologist_id": str(psychologist_user.id), "student_id": str(test_user.id)},
        headers=psychologist_headers,
    )
    assert response.status_code == 403


async def test_admin_creates_lists_and_deletes_assignment(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    created = await client.post(
        "/api/v1/admin/psychologist-assignments",
        json={"psychologist_id": str(psychologist_user.id), "student_id": str(test_user.id)},
        headers=admin_headers,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["psychologist_id"] == str(psychologist_user.id)
    assert body["student_id"] == str(test_user.id)
    assignment_id = body["id"]

    listed = await client.get(
        f"/api/v1/admin/psychologist-assignments?psychologist_id={psychologist_user.id}",
        headers=admin_headers,
    )
    assert listed.status_code == 200
    listed_body = listed.json()
    assert listed_body["total"] >= 1
    assert any(item["id"] == assignment_id for item in listed_body["items"])

    deleted = await client.delete(
        f"/api/v1/admin/psychologist-assignments/{assignment_id}",
        headers=admin_headers,
    )
    assert deleted.status_code == 204

    missing = await client.delete(
        f"/api/v1/admin/psychologist-assignments/{assignment_id}",
        headers=admin_headers,
    )
    assert missing.status_code == 404


async def test_create_assignment_rejects_duplicate(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    payload = {
        "psychologist_id": str(psychologist_user.id),
        "student_id": str(test_user.id),
    }
    first = await client.post(
        "/api/v1/admin/psychologist-assignments", json=payload, headers=admin_headers
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/admin/psychologist-assignments", json=payload, headers=admin_headers
    )
    assert second.status_code == 400
    assert "already exists" in second.json()["detail"].lower()


async def test_create_assignment_rejects_wrong_roles(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    admin_user: User,
    psychologist_user: User,
    test_user: User,
) -> None:
    # student_id points at a psychologist
    bad_student = await client.post(
        "/api/v1/admin/psychologist-assignments",
        json={
            "psychologist_id": str(psychologist_user.id),
            "student_id": str(psychologist_user.id),
        },
        headers=admin_headers,
    )
    assert bad_student.status_code == 400

    # psychologist_id points at a student
    bad_psych = await client.post(
        "/api/v1/admin/psychologist-assignments",
        json={"psychologist_id": str(test_user.id), "student_id": str(test_user.id)},
        headers=admin_headers,
    )
    assert bad_psych.status_code == 400

    # psychologist_id points at an admin
    bad_admin = await client.post(
        "/api/v1/admin/psychologist-assignments",
        json={"psychologist_id": str(admin_user.id), "student_id": str(test_user.id)},
        headers=admin_headers,
    )
    assert bad_admin.status_code == 400


async def test_create_assignment_rejects_missing_user(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    psychologist_user: User,
) -> None:
    response = await client.post(
        "/api/v1/admin/psychologist-assignments",
        json={
            "psychologist_id": str(psychologist_user.id),
            "student_id": str(uuid.uuid4()),
        },
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()
