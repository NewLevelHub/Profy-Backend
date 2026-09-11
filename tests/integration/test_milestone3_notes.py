"""Milestone 3 verification checklist (PRO-331).

Own-note CRUD, foreign note → 404, POST without assignment → 404, and soft
cutoff after unassign (no new POST; GET/PATCH/DELETE of old notes still ok).
Granular coverage also lives in test_psychologist_notes.py — this file is
the single end-to-end smoke for the ticket checklist.
"""

import httpx

from app.models.user import User, UserRole
from app.services import auth_service


async def test_milestone3_notes_checklist(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
    db_session,
) -> None:
    # POST without assignment → 404.
    assert (
        await client.post(
            f"/api/v1/psychologist/students/{test_user.id}/notes",
            json={"content": "too early"},
            headers=psychologist_headers,
        )
    ).status_code == 404

    assigned = await client.post(
        "/api/v1/admin/psychologist-assignments",
        json={
            "psychologist_id": str(psychologist_user.id),
            "student_id": str(test_user.id),
        },
        headers=admin_headers,
    )
    assert assigned.status_code == 201
    assignment_id = assigned.json()["id"]

    # Own-note CRUD.
    created = await client.post(
        f"/api/v1/psychologist/students/{test_user.id}/notes",
        json={"content": "checklist note"},
        headers=psychologist_headers,
    )
    assert created.status_code == 201
    note_id = created.json()["id"]

    listed = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}/notes",
        headers=psychologist_headers,
    )
    assert listed.status_code == 200
    assert any(n["id"] == note_id for n in listed.json())

    patched = await client.patch(
        f"/api/v1/psychologist/notes/{note_id}",
        json={"content": "checklist updated"},
        headers=psychologist_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["content"] == "checklist updated"

    # Foreign note → 404 (not 403).
    other = User(
        email="m3-other-psych@example.test",
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
    assert (
        await client.patch(
            f"/api/v1/psychologist/notes/{note_id}",
            json={"content": "nope"},
            headers=other_headers,
        )
    ).status_code == 404

    # Soft cutoff after unassign.
    assert (
        await client.delete(
            f"/api/v1/admin/psychologist-assignments/{assignment_id}",
            headers=admin_headers,
        )
    ).status_code == 204

    assert (
        await client.post(
            f"/api/v1/psychologist/students/{test_user.id}/notes",
            json={"content": "blocked"},
            headers=psychologist_headers,
        )
    ).status_code == 404

    assert (
        await client.get(
            f"/api/v1/psychologist/students/{test_user.id}/notes",
            headers=psychologist_headers,
        )
    ).status_code == 200
    assert (
        await client.patch(
            f"/api/v1/psychologist/notes/{note_id}",
            json={"content": "still ok"},
            headers=psychologist_headers,
        )
    ).status_code == 200
    assert (
        await client.delete(
            f"/api/v1/psychologist/notes/{note_id}",
            headers=psychologist_headers,
        )
    ).status_code == 204
