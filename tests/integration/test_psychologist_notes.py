"""Psychologist notes CRUD + soft cutoff (PRO-330 / checklist coverage for PRO-331).

Create requires an active assignment; list/PATCH/DELETE of own notes remain
allowed after the student is unassigned. Foreign note ids → 404, not 403.
"""

import httpx

from app.models.user import User


async def _assign(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> str:
    created = await client.post(
        "/api/v1/admin/psychologist-assignments",
        json={
            "psychologist_id": str(psychologist_user.id),
            "student_id": str(test_user.id),
        },
        headers=admin_headers,
    )
    assert created.status_code == 201
    return created.json()["id"]


async def test_create_note_requires_assignment(
    client: httpx.AsyncClient,
    psychologist_headers: dict[str, str],
    test_user: User,
) -> None:
    response = await client.post(
        f"/api/v1/psychologist/students/{test_user.id}/notes",
        json={"content": "Hello"},
        headers=psychologist_headers,
    )
    assert response.status_code == 404


async def test_notes_crud_happy_path(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await _assign(client, admin_headers, psychologist_user, test_user)

    created = await client.post(
        f"/api/v1/psychologist/students/{test_user.id}/notes",
        json={"content": "First note"},
        headers=psychologist_headers,
    )
    assert created.status_code == 201
    note = created.json()
    assert note["content"] == "First note"
    assert note["student_id"] == str(test_user.id)
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


async def test_soft_cutoff_keeps_existing_notes_after_unassign(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    assignment_id = await _assign(client, admin_headers, psychologist_user, test_user)

    created = await client.post(
        f"/api/v1/psychologist/students/{test_user.id}/notes",
        json={"content": "Kept after unassign"},
        headers=psychologist_headers,
    )
    assert created.status_code == 201
    note_id = created.json()["id"]

    deleted_assignment = await client.delete(
        f"/api/v1/admin/psychologist-assignments/{assignment_id}",
        headers=admin_headers,
    )
    assert deleted_assignment.status_code == 204

    # Soft cutoff: cannot create new notes without assignment.
    blocked = await client.post(
        f"/api/v1/psychologist/students/{test_user.id}/notes",
        json={"content": "Should fail"},
        headers=psychologist_headers,
    )
    assert blocked.status_code == 404

    # But existing notes remain readable / editable / deletable.
    listed = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}/notes",
        headers=psychologist_headers,
    )
    assert listed.status_code == 200
    assert any(item["id"] == note_id for item in listed.json())

    patched = await client.patch(
        f"/api/v1/psychologist/notes/{note_id}",
        json={"content": "Still editable"},
        headers=psychologist_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["content"] == "Still editable"

    deleted = await client.delete(
        f"/api/v1/psychologist/notes/{note_id}",
        headers=psychologist_headers,
    )
    assert deleted.status_code == 204


async def test_foreign_note_returns_404(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
    db_session,
) -> None:
    """Another psychologist's note id must not leak via 403."""
    from app.models.user import UserRole
    from app.services import auth_service

    other = User(
        email="other-psych@example.test",
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

    await _assign(client, admin_headers, psychologist_user, test_user)
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
