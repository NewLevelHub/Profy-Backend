"""Request limits of the auth endpoints that had none (SEC-15 and the audit's
rate-limiting notes): rejected Google tokens and code re-sends are budgeted
per client IP, and no limiter key keeps an email or an IP in the clear.
"""

import uuid

import pytest
import pytest_asyncio

from app.models.user import User
from app.routers import auth as auth_router
from app.services import auth_service, email_service
from app.services.oauth_service import google_id_token

GOOGLE = "/api/v1/auth/google"
RESEND = "/api/v1/auth/resend-verification"
FORGOT = "/api/v1/auth/forgot-password"
REGISTER = "/api/v1/auth/register"
ID_TOKEN = "x" * 200


@pytest_asyncio.fixture(autouse=True)
async def _clean_rate_limits():
    # Redis is not rolled back like the database fixture; start from zero
    # even when this module runs alone after a dev session.
    await auth_router._get_redis().flushdb()


@pytest.fixture(autouse=True)
def _no_outside_calls(monkeypatch):
    """Nothing here may reach a mail provider or Google."""

    async def _sent(*_args, **_kwargs) -> None:
        return None

    def _reject(*_args, **_kwargs):
        raise ValueError("bad token")

    monkeypatch.setattr(email_service, "send_verification_email", _sent)
    monkeypatch.setattr(email_service, "send_password_reset_email", _sent)
    monkeypatch.setattr(google_id_token, "verify_oauth2_token", _reject)


def _email() -> str:
    return f"{uuid.uuid4()}@example.com"


# --- /auth/google -----------------------------------------------------------


async def test_rejected_google_tokens_run_out_of_budget(client, monkeypatch):
    checked = []

    def _reject_and_count(token, *_args, **_kwargs):
        checked.append(token)
        raise ValueError("bad token")

    monkeypatch.setattr(google_id_token, "verify_oauth2_token", _reject_and_count)
    monkeypatch.setattr(auth_router, "_GOOGLE_IP_LIMIT", 3)

    statuses = [(await client.post(GOOGLE, json={"id_token": ID_TOKEN})).status_code for _ in range(5)]

    assert statuses == [400, 400, 400, 429, 429]
    # Past the limit the token is not even looked at.
    assert len(checked) == 3


async def test_successful_google_logins_do_not_spend_the_budget(client, monkeypatch):
    """A whole class signs in from one school IP: only rejected tokens count."""
    monkeypatch.setattr(auth_router, "_GOOGLE_IP_LIMIT", 3)

    for _ in range(6):
        claims = {"sub": str(uuid.uuid4()), "email": _email(), "email_verified": True}
        monkeypatch.setattr(google_id_token, "verify_oauth2_token", lambda *a, _c=claims, **kw: _c)
        response = await client.post(GOOGLE, json={"id_token": ID_TOKEN})
        assert response.status_code == 200

    assert await auth_router._get_redis().keys("google_ip:*") == []


# --- /auth/resend-verification ----------------------------------------------


async def test_resend_is_budgeted_per_ip_across_addresses(client, monkeypatch):
    """The per-address cooldown alone lets one client mail a whole list of
    addresses by changing the email in the request."""
    monkeypatch.setattr(auth_router, "_RESEND_IP_LIMIT", 3)

    statuses = [(await client.post(RESEND, json={"email": _email()})).status_code for _ in range(5)]

    assert statuses == [204, 204, 204, 429, 429]


async def test_resend_keeps_its_cooldown_per_address(client, db_session):
    user = User(email=_email(), hashed_password=auth_service.hash_password("Testpass123!"), is_verified=False)
    db_session.add(user)
    await db_session.flush()

    first = await client.post(RESEND, json={"email": user.email})
    second = await client.post(RESEND, json={"email": user.email})

    assert (first.status_code, second.status_code) == (204, 429)


# --- limiter keys -----------------------------------------------------------


async def test_no_limiter_key_holds_an_email_or_an_ip(client):
    """Redis is not where personal data should accumulate: every key is
    `<scope>:<keyed digest>`."""
    email = _email()
    await client.post(RESEND, json={"email": email})
    await client.post(FORGOT, json={"email": email})
    await client.post(REGISTER, json={"email": email, "password": "Testpass123!"})
    await client.post(GOOGLE, json={"id_token": ID_TOKEN})
    await client.post("/api/v1/auth/invitations/preview", json={"token": "t" * 43})
    await client.post("/api/v1/auth/invitations/accept", json={"token": "t" * 43, "password": "Testpass123!"})

    keys = await auth_router._get_redis().keys("*")

    assert keys, "the requests above must have left limiter keys"
    for key in keys:
        scope, _, digest = key.partition(":")
        assert scope and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), key
        assert "@" not in key and "127.0.0.1" not in key
