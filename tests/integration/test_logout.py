"""«Выйти» ends the session on the server (SEC-12): a token that was copied
out of the browser must not keep working until it expires."""

import uuid

import httpx
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.services import auth_service

ME = "/api/v1/auth/me"
LOGOUT = "/api/v1/auth/logout"
LOGIN = "/api/v1/auth/login"
PASSWORD = "Testpass123!"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _user(db: AsyncSession) -> User:
    user = User(
        email=f"{uuid.uuid4()}@example.com",
        hashed_password=auth_service.hash_password(PASSWORD),
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.commit()
    return user


async def test_logout_kills_the_token_that_called_it(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    user = await _user(db_session)
    token = auth_service.create_jwt_token(user)
    assert (await client.get(ME, headers=_bearer(token))).status_code == 200

    response = await client.post(LOGOUT, headers=_bearer(token))

    assert response.status_code == 204
    assert response.content == b""
    assert (await client.get(ME, headers=_bearer(token))).status_code == 401


async def test_logout_ends_every_session_of_the_account(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """A second device, or a copy of the token in someone else's hands, holds
    a token of its own — it goes too."""
    user = await _user(db_session)
    this_browser = (await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})).json()["access_token"]
    elsewhere = (await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})).json()["access_token"]

    assert (await client.post(LOGOUT, headers=_bearer(this_browser))).status_code == 204

    assert (await client.get(ME, headers=_bearer(this_browser))).status_code == 401
    assert (await client.get(ME, headers=_bearer(elsewhere))).status_code == 401


async def test_signing_in_again_after_logout_works(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    user = await _user(db_session)
    old = auth_service.create_jwt_token(user)
    await client.post(LOGOUT, headers=_bearer(old))

    login = await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})

    assert login.status_code == 200
    new = login.json()["access_token"]
    assert (await client.get(ME, headers=_bearer(new))).status_code == 200
    # The fresh token belongs to the next version; the old one stays dead.
    claims = jwt.decode(new, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert claims["ver"] == 1
    assert (await client.get(ME, headers=_bearer(old))).status_code == 401


async def test_a_dead_token_cannot_log_out_again(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    """Otherwise anyone holding an old token could keep signing the owner out."""
    user = await _user(db_session)
    token = auth_service.create_jwt_token(user)
    await client.post(LOGOUT, headers=_bearer(token))
    fresh = (await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})).json()["access_token"]

    assert (await client.post(LOGOUT, headers=_bearer(token))).status_code == 401
    assert (await client.get(ME, headers=_bearer(fresh))).status_code == 200


async def test_logout_does_not_touch_other_accounts(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    leaving, staying = await _user(db_session), await _user(db_session)
    staying_token = auth_service.create_jwt_token(staying)

    await client.post(LOGOUT, headers=_bearer(auth_service.create_jwt_token(leaving)))

    assert (await client.get(ME, headers=_bearer(staying_token))).status_code == 200
    await db_session.refresh(staying)
    assert staying.token_version == 0


async def test_logout_needs_a_session(client: httpx.AsyncClient) -> None:
    assert (await client.post(LOGOUT)).status_code in (401, 403)
    assert (await client.post(LOGOUT, headers=_bearer("not-a-token"))).status_code == 401
