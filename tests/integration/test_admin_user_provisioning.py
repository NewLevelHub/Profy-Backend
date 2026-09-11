"""POST /api/v1/admin/users — the first write endpoint admin ever had for
User rows (previously read + export only). Provisions admin/psychologist
accounts; self-registration (POST /auth/register) remains the only path
that creates a `student`."""

import uuid

import httpx


async def test_create_user_requires_admin(client: httpx.AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.post(
        "/api/v1/admin/users",
        json={"email": f"{uuid.uuid4()}@example.com", "password": "Testpass123!", "role": "psychologist"},
        headers=auth_headers,
    )
    assert response.status_code == 403


async def test_create_user_rejects_psychologist_caller(
    client: httpx.AsyncClient, psychologist_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/admin/users",
        json={"email": f"{uuid.uuid4()}@example.com", "password": "Testpass123!", "role": "psychologist"},
        headers=psychologist_headers,
    )
    assert response.status_code == 403


async def test_admin_creates_psychologist(
    client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> None:
    email = f"{uuid.uuid4()}@example.com"
    response = await client.post(
        "/api/v1/admin/users",
        json={"email": email, "password": "Testpass123!", "role": "psychologist"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == email
    assert body["role"] == "psychologist"
    assert body["is_admin"] is False
    assert body["is_verified"] is True


async def test_admin_creates_admin(client: httpx.AsyncClient, admin_headers: dict[str, str]) -> None:
    email = f"{uuid.uuid4()}@example.com"
    response = await client.post(
        "/api/v1/admin/users",
        json={"email": email, "password": "Testpass123!", "role": "admin"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "admin"
    assert body["is_admin"] is True


async def test_create_user_rejects_student_role(
    client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/admin/users",
        json={"email": f"{uuid.uuid4()}@example.com", "password": "Testpass123!", "role": "student"},
        headers=admin_headers,
    )
    assert response.status_code == 422


async def test_create_user_rejects_duplicate_email(
    client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> None:
    email = f"{uuid.uuid4()}@example.com"
    body = {"email": email, "password": "Testpass123!", "role": "psychologist"}
    first = await client.post("/api/v1/admin/users", json=body, headers=admin_headers)
    assert first.status_code == 201

    second = await client.post("/api/v1/admin/users", json=body, headers=admin_headers)
    assert second.status_code == 400


async def test_users_list_excludes_staff_accounts_by_default(
    client: httpx.AsyncClient, admin_headers: dict[str, str], test_user
) -> None:
    """GET /admin/users predates the role system — every row used to be a
    student. Now that admin/psychologist accounts exist, they shouldn't
    pollute this list unless explicitly asked for via ?role=."""
    psych_email = f"{uuid.uuid4()}@example.com"
    created = await client.post(
        "/api/v1/admin/users",
        json={"email": psych_email, "password": "Testpass123!", "role": "psychologist"},
        headers=admin_headers,
    )
    assert created.status_code == 201

    default_list = await client.get("/api/v1/admin/users?limit=100", headers=admin_headers)
    assert default_list.status_code == 200
    default_emails = {item["email"] for item in default_list.json()["items"]}
    assert psych_email not in default_emails
    assert test_user.email in default_emails  # the real student is still there

    filtered = await client.get("/api/v1/admin/users?role=psychologist&limit=100", headers=admin_headers)
    assert filtered.status_code == 200
    filtered_emails = {item["email"] for item in filtered.json()["items"]}
    assert psych_email in filtered_emails
    assert test_user.email not in filtered_emails
