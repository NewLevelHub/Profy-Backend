"""End-to-end smoke test for the fixture stack itself: real HTTP request
through the FastAPI app -> JWT auth -> transactional Postgres session ->
response. If this file passes, `client`/`db_session`/`auth_headers` are
wired correctly for every other test that will use them."""

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact import Artifact
from app.models.profile import Profile
from app.models.user import User

_BASE_PAYLOAD = {
    "name": "Аружан",
    "age": 15,
    "grade": 9,
    "city": "Алматы",
    "country": "Казахстан",
    "language": "ru",
    "subjects_liked": ["физика"],
}


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
    create_response = await client.post("/api/v1/profile", json=_BASE_PAYLOAD, headers=auth_headers)
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["user_id"] == str(test_user.id)
    assert created["name"] == "Аружан"
    # Backward compatible: omitting `artifacts` still returns an (empty)
    # `artifacts` key rather than requiring a follow-up call to discover that.
    assert created["artifacts"] == []

    get_response = await client.get("/api/v1/profile", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == created["id"]


async def test_combined_create_persists_profile_and_artifacts_atomically(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: AsyncSession,
) -> None:
    """Single POST /api/v1/profile with an `artifacts` payload must create
    both the Profile row and the Artifact rows in one shot, and the response
    must echo the saved artifacts so the frontend doesn't need a follow-up
    GET /profile/artifacts."""
    payload = {
        **_BASE_PAYLOAD,
        "artifacts": [
            {"type": "hobby", "value": "Шахматы"},
            {"type": "goal", "value": "Стать инженером"},
        ],
    }

    response = await client.post("/api/v1/profile", json=payload, headers=auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert {(item["type"], item["value"]) for item in body["artifacts"]} == {
        ("hobby", "Шахматы"),
        ("goal", "Стать инженером"),
    }

    # Confirm it's actually two real rows in the DB, not just an echo of the
    # request, and that the old standalone GET still sees them.
    get_response = await client.get("/api/v1/profile/artifacts", headers=auth_headers)
    assert get_response.status_code == 200
    assert {(item["type"], item["value"]) for item in get_response.json()["items"]} == {
        ("hobby", "Шахматы"),
        ("goal", "Стать инженером"),
    }

    result = await db_session.execute(select(Artifact).where(Artifact.profile_id == body["id"]))
    assert len(result.scalars().all()) == 2


async def test_combined_create_without_artifacts_leaves_artifacts_empty(
    client: httpx.AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """Clients that don't send `artifacts` at all (old two-step flow, or a
    user with nothing to report) must still get a 201 with an empty
    `artifacts` list — the field is optional, not required."""
    response = await client.post("/api/v1/profile", json=_BASE_PAYLOAD, headers=auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["artifacts"] == []

    result = await db_session.execute(select(Artifact).where(Artifact.profile_id == body["id"]))
    assert result.scalars().all() == []


async def test_combined_create_rejects_invalid_artifact_without_creating_profile(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: AsyncSession,
) -> None:
    """An invalid artifact entry (blank value) must fail the whole request —
    no half-created profile with no artifacts left behind."""
    payload = {
        **_BASE_PAYLOAD,
        "artifacts": [{"type": "hobby", "value": ""}],
    }

    response = await client.post("/api/v1/profile", json=payload, headers=auth_headers)
    assert response.status_code == 422

    result = await db_session.execute(select(Profile).where(Profile.user_id == test_user.id))
    assert result.scalar_one_or_none() is None


async def test_combined_create_conflict_when_profile_already_exists(
    client: httpx.AsyncClient, auth_headers: dict[str, str], test_user: User
) -> None:
    """Existing "profile already exists" 409 semantics are preserved when
    the request also carries an artifacts payload — and the second
    (rejected) request's artifacts must not overwrite the first one's."""
    first_payload = {**_BASE_PAYLOAD, "artifacts": [{"type": "hobby", "value": "Шахматы"}]}
    first = await client.post("/api/v1/profile", json=first_payload, headers=auth_headers)
    assert first.status_code == 201

    second_payload = {**_BASE_PAYLOAD, "artifacts": [{"type": "hobby", "value": "Плавание"}]}
    second = await client.post("/api/v1/profile", json=second_payload, headers=auth_headers)
    assert second.status_code == 409

    get_response = await client.get("/api/v1/profile/artifacts", headers=auth_headers)
    assert [item["value"] for item in get_response.json()["items"]] == ["Шахматы"]


async def test_get_profile_embeds_artifacts(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """GET /profile must echo the caller's artifacts inline (no follow-up
    GET /profile/artifacts needed to render the profile page)."""
    payload = {**_BASE_PAYLOAD, "artifacts": [{"type": "hobby", "value": "Шахматы"}]}
    create_response = await client.post("/api/v1/profile", json=payload, headers=auth_headers)
    assert create_response.status_code == 201

    get_response = await client.get("/api/v1/profile", headers=auth_headers)
    assert get_response.status_code == 200
    assert [item["value"] for item in get_response.json()["artifacts"]] == ["Шахматы"]


async def test_update_profile_with_artifacts_replaces_them_atomically(
    client: httpx.AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """PUT /profile with an `artifacts` payload must replace the existing
    set (delete-then-insert, same as POST /profile/artifacts) in the same
    transaction as the profile field update, and echo the new set in the
    response — mirroring the combined-create contract."""
    create_payload = {**_BASE_PAYLOAD, "artifacts": [{"type": "hobby", "value": "Шахматы"}]}
    create_response = await client.post("/api/v1/profile", json=create_payload, headers=auth_headers)
    assert create_response.status_code == 201
    profile_id = create_response.json()["id"]

    update_payload = {
        "name": "Айгерим",
        "artifacts": [{"type": "hobby", "value": "Плавание"}, {"type": "goal", "value": "Стать врачом"}],
    }
    update_response = await client.put("/api/v1/profile", json=update_payload, headers=auth_headers)
    assert update_response.status_code == 200
    body = update_response.json()
    assert body["name"] == "Айгерим"
    assert {(item["type"], item["value"]) for item in body["artifacts"]} == {
        ("hobby", "Плавание"),
        ("goal", "Стать врачом"),
    }

    result = await db_session.execute(select(Artifact).where(Artifact.profile_id == profile_id))
    assert {(a.type.value, a.value) for a in result.scalars().all()} == {
        ("hobby", "Плавание"),
        ("goal", "Стать врачом"),
    }


async def test_update_profile_without_artifacts_leaves_them_untouched(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Omitting `artifacts` on PUT must leave existing artifacts alone —
    the response still echoes the current (unchanged) set, same as GET."""
    create_payload = {**_BASE_PAYLOAD, "artifacts": [{"type": "hobby", "value": "Шахматы"}]}
    create_response = await client.post("/api/v1/profile", json=create_payload, headers=auth_headers)
    assert create_response.status_code == 201

    update_response = await client.put("/api/v1/profile", json={"name": "Айгерим"}, headers=auth_headers)
    assert update_response.status_code == 200
    body = update_response.json()
    assert body["name"] == "Айгерим"
    assert [item["value"] for item in body["artifacts"]] == ["Шахматы"]
