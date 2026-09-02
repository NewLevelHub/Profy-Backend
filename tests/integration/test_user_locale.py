"""users.locale — GET/PATCH /auth/me, seeding at registration, and the
first-time pre-fill from the profile's "language of instruction" field.
See docs/i18n-contract.md and ticket KZ-103.

Real HTTP through the app + transactional Postgres session (rolled back).
"""

import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

_PROFILE_PAYLOAD = {
    "name": "Аружан",
    "age": 15,
    "grade": 9,
    "city": "Алматы",
    "country": "Казахстан",
    "language": "русский",
    "subjects_liked": ["физика"],
}


async def test_me_returns_locale_defaulting_to_ru(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["locale"] == "ru"


async def test_patch_me_updates_locale(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    patch = await client.patch(
        "/api/v1/auth/me", json={"locale": "kk"}, headers=auth_headers
    )
    assert patch.status_code == 200
    assert patch.json()["locale"] == "kk"

    again = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert again.json()["locale"] == "kk"


async def test_patch_me_rejects_unknown_locale(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.patch(
        "/api/v1/auth/me", json={"locale": "en"}, headers=auth_headers
    )
    assert resp.status_code == 422


async def test_patch_me_requires_auth(client: httpx.AsyncClient) -> None:
    resp = await client.patch("/api/v1/auth/me", json={"locale": "kk"})
    assert resp.status_code == 401


async def test_register_seeds_locale_from_accept_language(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    email = f"{uuid.uuid4()}@example.com"
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Testpass123"},
        headers={"Accept-Language": "kk"},
    )
    assert resp.status_code == 201

    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    # "kk" is persisted even though it is not runtime-honored until KZ-603.
    assert user.locale == "kk"


async def test_register_defaults_locale_to_ru_without_header(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    email = f"{uuid.uuid4()}@example.com"
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Testpass123"},
    )
    assert resp.status_code == 201
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    assert user.locale == "ru"


async def test_profile_create_prefills_locale_from_language_field(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    payload = {**_PROFILE_PAYLOAD, "language": "казахский"}
    created = await client.post("/api/v1/profile", json=payload, headers=auth_headers)
    assert created.status_code == 201

    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me.json()["locale"] == "kk"


async def test_profile_create_does_not_override_explicit_locale(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    # User explicitly picked kk first...
    await client.patch("/api/v1/auth/me", json={"locale": "kk"}, headers=auth_headers)
    # ...then fills a profile that says the instruction language is Russian.
    payload = {**_PROFILE_PAYLOAD, "language": "русский"}
    created = await client.post("/api/v1/profile", json=payload, headers=auth_headers)
    assert created.status_code == 201

    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me.json()["locale"] == "kk"  # unchanged


async def test_profile_create_does_not_override_explicit_ru(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    # User explicitly switched to ru (e.g. kk -> ru) — same default value, but a
    # deliberate choice. `locale_explicit` must stop the profile pre-fill.
    await client.patch("/api/v1/auth/me", json={"locale": "ru"}, headers=auth_headers)
    payload = {**_PROFILE_PAYLOAD, "language": "казахский"}
    created = await client.post("/api/v1/profile", json=payload, headers=auth_headers)
    assert created.status_code == 201

    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me.json()["locale"] == "ru"  # not flipped to kk


async def test_patch_me_rejects_unknown_locale_via_validator(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    # The set is KNOWN_LOCALES, not a hardcoded Literal — "fr" is rejected the
    # same way, and adding a locale to KNOWN_LOCALES would let it through.
    resp = await client.patch(
        "/api/v1/auth/me", json={"locale": "fr"}, headers=auth_headers
    )
    assert resp.status_code == 422
