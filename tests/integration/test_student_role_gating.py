"""Student-facing routers (profile/assessment/etc.) used to only check
`get_current_user` — any authenticated account, including admin/psychologist
ones provisioned via POST /api/v1/admin/users (pro-281), could create a
Profile or take an assessment. Now gated on `get_current_student_user`
(app/dependencies.py). Covers a representative sample, not every router —
they all share the same dependency swap."""

import httpx


async def test_student_can_still_get_profile_404(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/profile", headers=auth_headers)
    assert response.status_code == 404  # no profile yet — proves the gate lets students through


async def test_admin_cannot_access_profile_endpoint(
    client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/profile", headers=admin_headers)
    assert response.status_code == 403


async def test_psychologist_cannot_access_profile_endpoint(
    client: httpx.AsyncClient, psychologist_headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/profile", headers=psychologist_headers)
    assert response.status_code == 403


async def test_admin_cannot_create_profile(
    client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/profile",
        json={
            "name": "Admin",
            "age": 16,
            "grade": 10,
            "city": "Астана",
            "country": "Казахстан",
            "language": "ru",
        },
        headers=admin_headers,
    )
    assert response.status_code == 403


async def test_admin_still_uses_me_endpoint_normally(
    client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> None:
    """/auth/me is not student-gated — every role needs it to see their own
    account (e.g. an admin/psychologist checking who they're logged in as)."""
    response = await client.get("/api/v1/auth/me", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
