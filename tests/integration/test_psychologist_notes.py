"""Psychologist notes CRUD (PRO-321 rework — no assignment step).

A psychologist can note any student. list/PATCH/DELETE only touch the
psychologist's own notes; a foreign note id → 404, never 403.
"""

import uuid

import httpx

from app.models.user import User, UserRole
from app.services import auth_service


async def test_create_note_for_any_student(
    client: httpx.AsyncClient,
    psychologist_headers: dict[str, str],
    test_user: User,
) -> None:
    response = await client.post(
        f"/api/v1/psychologist/students/{test_user.id}/notes",
        json={"content": "Hello"},
        headers=psychologist_headers,
    )
    assert response.status_code == 201
    assert response.json()["student_id"] == str(test_user.id)


async def test_create_note_for_unknown_student_404(
    client: httpx.AsyncClient, psychologist_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"/api/v1/psychologist/students/{uuid.uuid4()}/notes",
        json={"content": "nobody"},
        headers=psychologist_headers,
    )
    assert response.status_code == 404


async def test_notes_crud_happy_path(
    client: httpx.AsyncClient,
    psychologist_headers: dict[str, str],
    test_user: User,
) -> None:
    created = await client.post(
        f"/api/v1/psychologist/students/{test_user.id}/notes",
        json={"content": "First note"},
        headers=psychologist_headers,
    )
    assert created.status_code == 201
    note = created.json()
    assert note["content"] == "First note"
    note_id = note["id"]

    listed = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}/notes",
        headers=psychologist_headers,
    )
    assert listed.status_code == 200
    assert any(item["id"] == note_id for item in listed.json())

    patched = await client.patch(
        f"/api/v1/psychologist/notes/{note_id}",
        json={"content": "Updated note"},
        headers=psychologist_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["content"] == "Updated note"

    deleted = await client.delete(
        f"/api/v1/psychologist/notes/{note_id}",
        headers=psychologist_headers,
    )
    assert deleted.status_code == 204


async def test_foreign_note_returns_404(
    client: httpx.AsyncClient,
    psychologist_headers: dict[str, str],
    test_user: User,
    db_session,
) -> None:
    """Another psychologist's note id must not leak via 403."""
    other = User(
        email=f"{uuid.uuid4()}@example.com",
        hashed_password=auth_service.hash_password("Testpass123!"),
        is_active=True,
        is_verified=True,
        role=UserRole.psychologist,
    )
    db_session.add(other)
    await db_session.flush()
    other_headers = {
        "Authorization": f"Bearer {auth_service.create_jwt_token(other.id)}"
    }

    created = await client.post(
        f"/api/v1/psychologist/students/{test_user.id}/notes",
        json={"content": "Owner only"},
        headers=psychologist_headers,
    )
    assert created.status_code == 201
    note_id = created.json()["id"]

    assert (
        await client.patch(
            f"/api/v1/psychologist/notes/{note_id}",
            json={"content": "Hijack"},
            headers=other_headers,
        )
    ).status_code == 404
    assert (
        await client.delete(
            f"/api/v1/psychologist/notes/{note_id}",
            headers=other_headers,
        )
    ).status_code == 404


async def test_notes_require_psychologist_role(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    test_user: User,
) -> None:
    assert (
        await client.get(
            f"/api/v1/psychologist/students/{test_user.id}/notes",
            headers=auth_headers,
        )
    ).status_code == 403
    assert (
        await client.get(
            f"/api/v1/psychologist/students/{test_user.id}/notes",
            headers=admin_headers,
        )
    ).status_code == 403
