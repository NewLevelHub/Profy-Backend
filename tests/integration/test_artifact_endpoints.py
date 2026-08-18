"""Regression coverage for the standalone POST/GET /api/v1/profile/artifacts
endpoints — added alongside the combined profile+artifacts create endpoint
(app/routers/profile.py::create_profile) to prove that flow is purely
additive and the pre-existing two-step onboarding path (create profile,
then save artifacts separately) still works unchanged."""

import httpx

from app.models.user import User


async def test_save_artifacts_requires_profile_first(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/profile/artifacts",
        json={"items": [{"type": "hobby", "value": "Шахматы"}]},
        headers=auth_headers,
    )
    assert response.status_code == 404


async def test_get_artifacts_requires_profile_first(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/profile/artifacts", headers=auth_headers)
    assert response.status_code == 404


async def test_two_step_flow_create_profile_then_save_artifacts(
    client: httpx.AsyncClient, auth_headers: dict[str, str], test_user: User
) -> None:
    profile_payload = {
        "name": "Данияр",
        "age": 12,
        "grade": 6,
        "city": "Астана",
        "country": "Казахстан",
        "language": "ru",
    }
    create_response = await client.post("/api/v1/profile", json=profile_payload, headers=auth_headers)
    assert create_response.status_code == 201
    assert create_response.json()["artifacts"] == []

    save_response = await client.post(
        "/api/v1/profile/artifacts",
        json={"items": [{"type": "club", "value": "Робототехника"}]},
        headers=auth_headers,
    )
    assert save_response.status_code == 200
    assert save_response.json()["items"] == [{"type": "club", "value": "Робототехника"}]

    get_response = await client.get("/api/v1/profile/artifacts", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["items"] == [{"type": "club", "value": "Робототехника"}]


async def test_save_artifacts_replaces_previous_selection(
    client: httpx.AsyncClient, auth_headers: dict[str, str], test_user: User
) -> None:
    profile_payload = {
        "name": "Данияр",
        "age": 12,
        "grade": 6,
        "city": "Астана",
        "country": "Казахстан",
        "language": "ru",
    }
    await client.post("/api/v1/profile", json=profile_payload, headers=auth_headers)

    await client.post(
        "/api/v1/profile/artifacts",
        json={"items": [{"type": "hobby", "value": "Шахматы"}]},
        headers=auth_headers,
    )
    replace_response = await client.post(
        "/api/v1/profile/artifacts",
        json={"items": [{"type": "sport", "value": "Плавание"}]},
        headers=auth_headers,
    )
    assert replace_response.status_code == 200

    get_response = await client.get("/api/v1/profile/artifacts", headers=auth_headers)
    assert get_response.json()["items"] == [{"type": "sport", "value": "Плавание"}]
