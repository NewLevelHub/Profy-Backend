"""Brute-force protection of the six-digit emailed codes (SEC-02): password
reset and email verification.

Two independent layers, each tested with the other lifted out of the way:
the code itself burns after `MAX_CODE_ATTEMPTS` wrong guesses (database), and
failed guesses are budgeted per email and per client IP (Redis).
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.models.email_verification import EmailVerificationToken
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.routers import auth as auth_router
from app.services import auth_service, email_service, invitation_service, password_reset_service, token_utils
from app.services.token_utils import MAX_CODE_ATTEMPTS, hash_code

CODE = "123456"
WRONG = "654321"
OLD_PASSWORD = "OldPassword123!"
NEW_PASSWORD = "NewPassword456!"

VERIFY_RESET = "/api/v1/auth/verify-reset-code"
RESET = "/api/v1/auth/reset-password"
VERIFY_EMAIL = "/api/v1/auth/verify-email"


@pytest_asyncio.fixture(autouse=True)
async def _clean_rate_limits():
    # Redis is not rolled back like the database fixture; start from zero
    # even when this module runs alone after a dev session.
    await auth_router._get_redis().flushdb()


@pytest.fixture
def no_rate_limits(monkeypatch):
    monkeypatch.setattr(auth_router, "_CODE_EMAIL_LIMIT", 1000)
    monkeypatch.setattr(auth_router, "_CODE_IP_LIMIT", 1000)


@pytest.fixture
def unburnable_codes(monkeypatch):
    monkeypatch.setattr(token_utils, "MAX_CODE_ATTEMPTS", 1000)


def _email() -> str:
    return f"{uuid.uuid4()}@example.com"


async def _user(db_session, *, is_verified: bool = True) -> User:
    user = User(
        email=_email(),
        hashed_password=auth_service.hash_password(OLD_PASSWORD),
        is_active=True,
        is_verified=is_verified,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _issue(db_session, model, user: User, code: str = CODE):
    token = model(
        user_id=user.id,
        code_hash=hash_code(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db_session.add(token)
    await db_session.commit()
    return token


def _reset_body(email: str, code: str) -> dict:
    return {"email": email, "code": code, "new_password": NEW_PASSWORD}


def _code_body(email: str, code: str) -> dict:
    return {"email": email, "code": code}


# --- the code burns ---------------------------------------------------------


async def test_reset_code_burns_after_wrong_guesses_spread_over_both_endpoints(
    client, db_session, no_rate_limits
):
    user = await _user(db_session)
    token = await _issue(db_session, PasswordResetToken, user)

    statuses = []
    for _ in range(3):
        statuses.append((await client.post(VERIFY_RESET, json=_code_body(user.email, WRONG))).status_code)
    for _ in range(MAX_CODE_ATTEMPTS - 3):
        statuses.append((await client.post(RESET, json=_reset_body(user.email, WRONG))).status_code)
    assert statuses == [400] * MAX_CODE_ATTEMPTS

    await db_session.refresh(token)
    assert token.attempts == MAX_CODE_ATTEMPTS
    assert token.used_at is not None

    # The right code no longer opens anything, on either endpoint.
    assert (await client.post(VERIFY_RESET, json=_code_body(user.email, CODE))).status_code == 400
    assert (await client.post(RESET, json=_reset_body(user.email, CODE))).status_code == 400
    await db_session.refresh(user)
    assert user.token_version == 0
    assert auth_service.verify_password(OLD_PASSWORD, user.hashed_password)


async def test_reset_code_works_on_the_last_remaining_attempt(client, db_session, no_rate_limits):
    user = await _user(db_session)
    token = await _issue(db_session, PasswordResetToken, user)

    for _ in range(MAX_CODE_ATTEMPTS - 1):
        assert (await client.post(VERIFY_RESET, json=_code_body(user.email, WRONG))).status_code == 400
    await db_session.refresh(token)
    assert token.attempts == MAX_CODE_ATTEMPTS - 1
    assert token.used_at is None

    assert (await client.post(VERIFY_RESET, json=_code_body(user.email, CODE))).status_code == 200
    assert (await client.post(RESET, json=_reset_body(user.email, CODE))).status_code == 200
    await db_session.refresh(user)
    assert auth_service.verify_password(NEW_PASSWORD, user.hashed_password)


async def test_reissued_reset_code_starts_with_a_fresh_budget(
    client, db_session, no_rate_limits, monkeypatch
):
    user = await _user(db_session)
    await _issue(db_session, PasswordResetToken, user)
    for _ in range(MAX_CODE_ATTEMPTS):
        await client.post(VERIFY_RESET, json=_code_body(user.email, WRONG))

    sent = {}

    async def _capture(email, code, **kwargs):
        sent["code"] = code

    monkeypatch.setattr(email_service, "send_password_reset_email", _capture)
    await password_reset_service.initiate_reset(user.email, db_session)

    assert (await client.post(RESET, json=_reset_body(user.email, sent["code"]))).status_code == 200


async def test_verification_code_burns_after_wrong_guesses(client, db_session, no_rate_limits):
    user = await _user(db_session, is_verified=False)
    token = await _issue(db_session, EmailVerificationToken, user)

    for _ in range(MAX_CODE_ATTEMPTS):
        assert (await client.post(VERIFY_EMAIL, json=_code_body(user.email, WRONG))).status_code == 400
    await db_session.refresh(token)
    assert token.attempts == MAX_CODE_ATTEMPTS
    assert token.used_at is not None

    assert (await client.post(VERIFY_EMAIL, json=_code_body(user.email, CODE))).status_code == 400
    await db_session.refresh(user)
    assert user.is_verified is False


async def test_verification_code_works_on_the_last_remaining_attempt(client, db_session, no_rate_limits):
    user = await _user(db_session, is_verified=False)
    await _issue(db_session, EmailVerificationToken, user)

    for _ in range(MAX_CODE_ATTEMPTS - 1):
        assert (await client.post(VERIFY_EMAIL, json=_code_body(user.email, WRONG))).status_code == 400

    response = await client.post(VERIFY_EMAIL, json=_code_body(user.email, CODE))
    assert response.status_code == 200
    assert response.json()["access_token"]


# --- the failure budget -----------------------------------------------------


async def test_reset_endpoints_share_one_failure_budget_per_email(client, db_session, unburnable_codes):
    user = await _user(db_session)
    await _issue(db_session, PasswordResetToken, user)
    limit = auth_router._CODE_EMAIL_LIMIT

    statuses = []
    for _ in range(3):
        statuses.append((await client.post(VERIFY_RESET, json=_code_body(user.email, WRONG))).status_code)
    for _ in range(limit - 3):
        statuses.append((await client.post(RESET, json=_reset_body(user.email, WRONG))).status_code)
    assert statuses == [400] * limit

    # Out of budget on both endpoints — the right code included.
    blocked = await client.post(VERIFY_RESET, json=_code_body(user.email, CODE))
    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["Retry-After"]) <= auth_router._CODE_WINDOW
    assert (await client.post(RESET, json=_reset_body(user.email, CODE))).status_code == 429

    keys = await auth_router._get_redis().keys("*")
    assert keys and all(user.email not in key and "127.0.0.1" not in key for key in keys)


async def test_email_budget_ignores_address_case(client, db_session, unburnable_codes, monkeypatch):
    monkeypatch.setattr(auth_router, "_CODE_EMAIL_LIMIT", 2)
    user = await _user(db_session)
    await _issue(db_session, PasswordResetToken, user)

    statuses = [
        (await client.post(VERIFY_RESET, json=_code_body(email, WRONG))).status_code
        for email in (user.email.upper(), user.email.title(), user.email)
    ]
    assert statuses == [400, 400, 429]


@pytest.mark.parametrize("path", [VERIFY_RESET, RESET, VERIFY_EMAIL])
async def test_unknown_address_is_limited_exactly_like_a_real_one(client, path):
    email = _email()
    body = _reset_body(email, WRONG) if path == RESET else _code_body(email, WRONG)
    limit = auth_router._CODE_EMAIL_LIMIT

    statuses = [(await client.post(path, json=body)).status_code for _ in range(limit + 1)]
    assert statuses == [400] * limit + [429]


@pytest.mark.parametrize("path", [VERIFY_RESET, RESET, VERIFY_EMAIL])
async def test_ip_budget_spans_different_accounts(client, path, monkeypatch):
    monkeypatch.setattr(auth_router, "_CODE_IP_LIMIT", 3)

    statuses = []
    for _ in range(4):
        email = _email()
        body = _reset_body(email, WRONG) if path == RESET else _code_body(email, WRONG)
        statuses.append((await client.post(path, json=body)).status_code)
    assert statuses == [400, 400, 400, 429]


async def test_correct_codes_do_not_spend_the_ip_budget(client, db_session, monkeypatch):
    # A class behind one school address, everyone entering their own code.
    monkeypatch.setattr(auth_router, "_CODE_IP_LIMIT", 2)

    for _ in range(4):
        user = await _user(db_session, is_verified=False)
        await _issue(db_session, EmailVerificationToken, user)
        assert (await client.post(VERIFY_EMAIL, json=_code_body(user.email, CODE))).status_code == 200


async def test_successful_reset_clears_the_email_failures_but_not_the_ip_ones(
    client, db_session, unburnable_codes
):
    user = await _user(db_session)
    await _issue(db_session, PasswordResetToken, user)
    for _ in range(auth_router._CODE_EMAIL_LIMIT - 1):
        await client.post(VERIFY_RESET, json=_code_body(user.email, WRONG))

    assert (await client.post(RESET, json=_reset_body(user.email, CODE))).status_code == 200

    redis = auth_router._get_redis()
    assert await redis.keys("reset_code_email:*") == []
    ip_keys = await redis.keys("reset_code_ip:*")
    assert len(ip_keys) == 1
    assert int(await redis.get(ip_keys[0])) == auth_router._CODE_EMAIL_LIMIT - 1


async def test_reset_and_verification_budgets_are_separate(client, db_session, unburnable_codes):
    user = await _user(db_session, is_verified=False)
    await _issue(db_session, EmailVerificationToken, user)
    for _ in range(auth_router._CODE_EMAIL_LIMIT):
        await client.post(VERIFY_RESET, json=_code_body(user.email, WRONG))

    assert (await client.post(VERIFY_EMAIL, json=_code_body(user.email, CODE))).status_code == 200


# --- the stored hash --------------------------------------------------------


def test_code_hash_is_keyed_and_cannot_be_rebuilt_from_the_code_alone():
    assert hash_code(CODE) != hashlib.sha256(CODE.encode()).hexdigest()
    assert hash_code(CODE) == hash_code(CODE)
    assert len(hash_code(CODE)) == 64
    assert token_utils.code_matches(hash_code(CODE), CODE)
    assert not token_utils.code_matches(hash_code(CODE), WRONG)


def test_invitation_link_hash_is_unchanged_so_open_links_keep_working():
    token = "link-token"
    assert invitation_service.hash_token(token) == hashlib.sha256(token.encode()).hexdigest()
