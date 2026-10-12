"""GET /api/v1/admin/users role filter. Staff accounts are created only by
accepting an invitation (PRO-457); the password-based POST /admin/users is
gone (PRO-466)."""

import uuid

import httpx


async def test_password_based_staff_creation_is_gone(
    client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/admin/users",
        json={"email": f"{uuid.uuid4()}@example.com", "password": "Testpass123!", "role": "psychologist"},
        headers=admin_headers,
    )
    assert response.status_code == 405


async def test_users_list_excludes_staff_accounts_by_default(
    client: httpx.AsyncClient, admin_headers: dict[str, str], test_user, psychologist_user
) -> None:
    """GET /admin/users predates the role system — every row used to be a
    student. Now that admin/psychologist accounts exist, they shouldn't
    pollute this list unless explicitly asked for via ?role=."""
    psych_email = psychologist_user.email

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
