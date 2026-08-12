"""End-to-end smoke test for the fixture stack itself: real HTTP request
through the FastAPI app -> JWT auth -> transactional Postgres session ->
response. If this file passes, `client`/`db_session`/`auth_headers` are
wired correctly for every other test that will use them."""

import httpx

from app.models.user import User


async def test_get_profile_requires_auth(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/profile")
    assert response.status_code == 401


async def test_get_profile_404_when_none_created(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/profile", headers=auth_headers)
    assert response.status_code == 404


async def test_create_then_get_profile_roundtrips_through_db(
    client: httpx.AsyncClient, auth_headers: dict[str, str], test_user: User
) -> None:
    payload = {
        "name": "Аружан",
        "age": 15,
        "grade": 9,
        "city": "Алматы",
        "country": "Казахстан",
        "language": "ru",
        "subjects_liked": ["физика"],
    }

    create_response = await client.post("/api/v1/profile", json=payload, headers=auth_headers)
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["user_id"] == str(test_user.id)
    assert created["name"] == "Аружан"

    get_response = await client.get("/api/v1/profile", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == created["id"]
