"""Regression test for a case-mismatch bug: a user who registers with a
mixed-case email (as typed in a signup form) and later signs in with Google
must link to that same account, not create a duplicate. Fixed by normalizing
email to lowercase at the request schema boundary
(app/schemas/auth.py::NormalizedEmail) and on the Google claim email in
oauth_service.login_or_register_google."""

import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services import oauth_service
from app.services.oauth_service import google_id_token


async def test_google_login_links_to_account_registered_with_different_email_casing(
    client: httpx.AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    typed_email = f"Test.{uuid.uuid4().hex}@Gmail.com"
    canonical_email = typed_email.lower()

    register_response = await client.post(
        "/api/v1/auth/register",
        json={"email": typed_email, "password": "Testpass123!"},
    )
    assert register_response.status_code == 201

    stored = (
        await db_session.execute(select(User).where(User.email == canonical_email))
    ).scalar_one()
    assert stored.email == canonical_email  # normalized on write, not stored mixed-case

    sub = str(uuid.uuid4())
    monkeypatch.setattr(
        google_id_token,
        "verify_oauth2_token",
        lambda *a, **kw: {"sub": sub, "email": canonical_email, "email_verified": True},
    )

    user, _ = await oauth_service.login_or_register_google("fake-token", db_session)

    assert user.id == stored.id  # linked to the existing account, not duplicated
    rows = (
        await db_session.execute(select(User).where(User.email == canonical_email))
    ).scalars().all()
    assert len(rows) == 1
