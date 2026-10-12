"""Account enumeration through the auth endpoints (SEC-07).

`/login` may still say that an address signs in with Google (the form needs
it), but each such answer costs a failed attempt. `/verify-email` gives one
answer for every way a code can be rejected.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.i18n.catalog import api_errors
from app.models.email_verification import EmailVerificationToken
from app.models.user import User
from app.routers import auth as auth_router
from app.services import auth_service
from app.services.token_utils import hash_code

LOGIN = "/api/v1/auth/login"
VERIFY_EMAIL = "/api/v1/auth/verify-email"
PASSWORD = "Testpass123!"
CODE = "123456"
WRONG = "654321"


@pytest_asyncio.fixture(autouse=True)
async def _clean_rate_limits():
    # Redis is not rolled back like the database fixture; start from zero
    # even when this module runs alone after a dev session.
    await auth_router._get_redis().flushdb()


def _email() -> str:
    return f"{uuid.uuid4()}@example.com"


async def _user(db_session, *, password: str | None = PASSWORD, is_verified: bool = True) -> User:
    user = User(
        email=_email(),
        hashed_password=auth_service.hash_password(password) if password else None,
        google_id=None if password else str(uuid.uuid4()),
        is_active=True,
        is_verified=is_verified,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _issue_code(db_session, user: User, *, expires_in: timedelta = timedelta(minutes=15)) -> None:
    db_session.add(
        EmailVerificationToken(
            user_id=user.id,
            code_hash=hash_code(CODE),
            expires_at=datetime.now(timezone.utc) + expires_in,
        )
    )
    await db_session.commit()


# --- /login -----------------------------------------------------------------


async def test_probing_a_google_account_spends_the_email_budget(client, db_session, monkeypatch):
    monkeypatch.setattr(auth_router, "_LOGIN_EMAIL_LIMIT", 2)
    monkeypatch.setattr(auth_router, "_LOGIN_IP_LIMIT", 100)
    user = await _user(db_session, password=None)
    await db_session.commit()

    responses = [
        await client.post(LOGIN, json={"email": user.email, "password": "anything"}) for _ in range(3)
    ]

    assert [response.status_code for response in responses] == [403, 403, 429]
    assert responses[0].json()["detail"] == {"detail": "google_account", "email": user.email}


async def test_probing_google_accounts_spends_the_ip_budget_across_addresses(
    client, db_session, monkeypatch
):
    monkeypatch.setattr(auth_router, "_LOGIN_IP_LIMIT", 2)
    monkeypatch.setattr(auth_router, "_LOGIN_EMAIL_LIMIT", 100)
    users = [await _user(db_session, password=None) for _ in range(3)]
    await db_session.commit()

    statuses = [
        (await client.post(LOGIN, json={"email": user.email, "password": "anything"})).status_code
        for user in users
    ]

    assert statuses == [403, 403, 429]


async def test_right_password_on_an_unverified_account_spends_nothing(client, db_session, monkeypatch):
    # The password matched, so nothing is being guessed: the person is sent
    # to enter their code and must not be locked out of logging in for it.
    monkeypatch.setattr(auth_router, "_LOGIN_EMAIL_LIMIT", 2)
    monkeypatch.setattr(auth_router, "_LOGIN_IP_LIMIT", 2)
    user = await _user(db_session, is_verified=False)
    await db_session.commit()

    responses = [
        await client.post(LOGIN, json={"email": user.email, "password": PASSWORD}) for _ in range(4)
    ]

    assert [response.status_code for response in responses] == [403] * 4
    assert responses[0].json()["detail"] == {"detail": "email_not_verified", "email": user.email}
    assert await auth_router._get_redis().keys("login_*") == []


async def test_wrong_password_on_an_unverified_account_looks_like_any_wrong_password(client, db_session):
    user = await _user(db_session, is_verified=False)
    await db_session.commit()

    known = await client.post(LOGIN, json={"email": user.email, "password": "wrong-password"})
    unknown = await client.post(LOGIN, json={"email": _email(), "password": "wrong-password"})

    assert known.status_code == unknown.status_code == 401
    assert known.json() == unknown.json()


# --- /verify-email ----------------------------------------------------------


async def _unknown_address(db_session) -> str:
    return _email()


async def _verified_account(db_session) -> str:
    user = await _user(db_session)
    await db_session.commit()
    return user.email


async def _account_without_a_code(db_session) -> str:
    user = await _user(db_session, is_verified=False)
    await db_session.commit()
    return user.email


async def _account_with_an_expired_code(db_session) -> str:
    user = await _user(db_session, is_verified=False)
    await _issue_code(db_session, user, expires_in=timedelta(minutes=-1))
    return user.email


async def _account_with_a_live_code(db_session) -> str:
    user = await _user(db_session, is_verified=False)
    await _issue_code(db_session, user)
    return user.email


@pytest.mark.parametrize(
    "scenario",
    [
        _unknown_address,
        _verified_account,
        _account_without_a_code,
        _account_with_an_expired_code,
        _account_with_a_live_code,
    ],
)
async def test_every_rejected_code_gets_the_same_answer(client, db_session, scenario):
    email = await scenario(db_session)

    response = await client.post(VERIFY_EMAIL, json={"email": email, "code": WRONG})

    assert response.status_code == 400
    assert response.json() == {"detail": api_errors.RU["invalid_or_expired_code"]}
    assert "retry-after" not in response.headers


async def test_the_right_code_still_verifies(client, db_session):
    email = await _account_with_a_live_code(db_session)

    response = await client.post(VERIFY_EMAIL, json={"email": email, "code": CODE})

    assert response.status_code == 200
    assert response.json()["user"]["email"] == email
