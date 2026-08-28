"""Google OAuth login: new-account creation, existing-password-account
linking by email, re-login of an existing google account, the
email_verified guard, and the login() 403 guard for google-only accounts.
`verify_oauth2_token` is monkeypatched on the imported google_id_token
module object, same pattern used for email_service in
test_auth_email_resilience.py."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services import auth_service, oauth_service
from app.services.oauth_service import google_id_token


def _fake_claims(email: str, sub: str, email_verified: bool = True) -> dict:
    return {"sub": sub, "email": email, "email_verified": email_verified}


async def test_login_or_register_google_creates_new_user(
    db_session: AsyncSession, monkeypatch
) -> None:
    email = f"{uuid.uuid4()}@example.test"
    sub = str(uuid.uuid4())
    monkeypatch.setattr(
        google_id_token, "verify_oauth2_token", lambda *a, **kw: _fake_claims(email, sub)
    )

    user, token = await oauth_service.login_or_register_google("fake-token", db_session)

    assert token
    assert user.email == email
    assert user.google_id == sub
    assert user.hashed_password is None
    assert user.is_verified is True


async def test_login_or_register_google_links_existing_password_account(
    db_session: AsyncSession, monkeypatch
) -> None:
    email = f"{uuid.uuid4()}@example.test"
    existing = User(
        email=email,
        hashed_password=auth_service.hash_password("Testpass123!"),
        is_active=True,
        is_verified=False,
    )
    db_session.add(existing)
    await db_session.commit()
    await db_session.refresh(existing)

    sub = str(uuid.uuid4())
    monkeypatch.setattr(
        google_id_token, "verify_oauth2_token", lambda *a, **kw: _fake_claims(email, sub)
    )

    user, _ = await oauth_service.login_or_register_google("fake-token", db_session)

    assert user.id == existing.id
    assert user.google_id == sub
    assert user.is_verified is True
    assert user.hashed_password is not None  # password preserved, not wiped


async def test_login_or_register_google_relogs_in_existing_google_user(
    db_session: AsyncSession, monkeypatch
) -> None:
    email = f"{uuid.uuid4()}@example.test"
    sub = str(uuid.uuid4())
    monkeypatch.setattr(
        google_id_token, "verify_oauth2_token", lambda *a, **kw: _fake_claims(email, sub)
    )

    first_user, _ = await oauth_service.login_or_register_google("fake-token", db_session)
    second_user, _ = await oauth_service.login_or_register_google("fake-token", db_session)

    assert first_user.id == second_user.id

    rows = (
        await db_session.execute(select(User).where(User.google_id == sub))
    ).scalars().all()
    assert len(rows) == 1


async def test_verify_google_id_token_rejects_unverified_email(monkeypatch) -> None:
    monkeypatch.setattr(
        google_id_token,
        "verify_oauth2_token",
        lambda *a, **kw: _fake_claims("x@example.test", "sub-1", email_verified=False),
    )

    with pytest.raises(ValueError):
        await oauth_service.verify_google_id_token("fake-token")


async def test_login_rejects_password_for_google_only_account(
    db_session: AsyncSession,
) -> None:
    email = f"{uuid.uuid4()}@example.test"
    user = User(
        email=email,
        hashed_password=None,
        google_id=str(uuid.uuid4()),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(LookupError, match=f"google_account:{email}"):
        await auth_service.login(email, "any-password", db_session)
