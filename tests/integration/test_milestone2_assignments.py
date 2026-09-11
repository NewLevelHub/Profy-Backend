"""Milestone 2 verification checklist (PRO-328).

Mirrors docs/user-roles-integration-plan.md §Проверка for psychologist
assignments: empty list before assign, non-empty after, 404 for an
unassigned student, 403 for non-psychologist callers, 4xx on bad roles
in admin POST. Granular coverage also lives in
test_admin_psychologist_assignments.py and test_psychologist_students.py —
this file is the single end-to-end smoke the plan describes.
"""

import httpx

from app.models.user import User


async def test_milestone2_assignment_round_trip(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
    admin_user: User,
) -> None:
    # Non-psychologist cannot hit psychologist routes.
    assert (
        await client.get("/api/v1/psychologist/students", headers=auth_headers)
    ).status_code == 403
    assert (
        await client.get("/api/v1/psychologist/students", headers=admin_headers)
    ).status_code == 403

    # Empty before assignment.
    before = await client.get(
        "/api/v1/psychologist/students", headers=psychologist_headers
    )
    assert before.status_code == 200
    assert before.json() == []

    # Unassigned student detail → 404 (not 403).
    unassigned = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}",
        headers=psychologist_headers,
    )
    assert unassigned.status_code == 404

    # Wrong roles on admin POST → 4xx.
    bad_roles = await client.post(
        "/api/v1/admin/psychologist-assignments",
        json={
            "psychologist_id": str(admin_user.id),
            "student_id": str(test_user.id),
        },
        headers=admin_headers,
    )
    assert 400 <= bad_roles.status_code < 500

    # Assign, then list is non-empty and detail works.
    created = await client.post(
        "/api/v1/admin/psychologist-assignments",
        json={
            "psychologist_id": str(psychologist_user.id),
            "student_id": str(test_user.id),
        },
        headers=admin_headers,
    )
    assert created.status_code == 201

    after = await client.get(
        "/api/v1/psychologist/students", headers=psychologist_headers
    )
    assert after.status_code == 200
    items = after.json()
    assert len(items) == 1
    assert items[0]["id"] == str(test_user.id)

    detail = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}",
        headers=psychologist_headers,
    )
    assert detail.status_code == 200
    assert detail.json()["id"] == str(test_user.id)
