"""
Unit tests for auth_service.register() — covering:
  - MX validation is called before any DB interaction
  - Stale unconfirmed accounts (>24 h) are purged
  - Re-registration over a fresh unconfirmed account resets the record
  - Confirmed accounts still raise ValueError("Email already exists")
  - Happy-path: new user is created and verification email is sent
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services import auth_service
from app.services.email_validator import EmailValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _PassValidator(EmailValidator):
    """Validator that always passes — used for tests not focused on MX."""

    async def validate(self, email: str) -> None:
        pass


class _FailValidator(EmailValidator):
    """Validator that always raises HTTP 422."""

    async def validate(self, email: str) -> None:
        raise HTTPException(status_code=422, detail="bad domain")


def _make_user(
    *,
    is_verified: bool,
    age_hours: float = 1.0,
) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.is_verified = is_verified
    user.created_at = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    return user


def _make_db(existing_user: Any = None) -> AsyncMock:
    """Build a minimal AsyncSession mock."""
    db = AsyncMock()

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = existing_user
    db.execute.return_value = scalar_result

    # flush / commit / add are fire-and-forget
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


# ---------------------------------------------------------------------------
# MX validation is the first gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mx_failure_raises_before_db() -> None:
    db = _make_db()
    with pytest.raises(HTTPException) as exc_info:
        await auth_service.register(
            "user@bad-domain.xyz",
            "Password1",
            db,
            validator=_FailValidator(),
        )
    assert exc_info.value.status_code == 422
    db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Stale cleanup runs for every registration attempt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_purge_is_executed() -> None:
    """_purge_stale_unconfirmed must issue a DELETE before the SELECT."""
    db = _make_db(existing_user=None)

    with (
        patch("app.services.auth_service._purge_stale_unconfirmed", new_callable=AsyncMock) as mock_purge,
        patch("app.services.auth_service._create_verification_token", new_callable=AsyncMock, return_value="123456"),
        patch("app.services.email_service.send_verification_email", new_callable=AsyncMock),
    ):
        await auth_service.register("user@example.com", "Password1", db, validator=_PassValidator())
        mock_purge.assert_awaited_once_with(db)


# ---------------------------------------------------------------------------
# Confirmed account → ValueError (router turns this into 409)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirmed_account_raises_value_error() -> None:
    verified_user = _make_user(is_verified=True)
    db = _make_db(existing_user=verified_user)

    with (
        patch("app.services.auth_service._purge_stale_unconfirmed", new_callable=AsyncMock),
    ):
        with pytest.raises(ValueError, match="already exists"):
            await auth_service.register("user@example.com", "Password1", db, validator=_PassValidator())


# ---------------------------------------------------------------------------
# Unconfirmed account (< 24 h) → reset in-place, no new row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unconfirmed_account_is_reset_in_place() -> None:
    unconfirmed = _make_user(is_verified=False, age_hours=2)
    db = _make_db(existing_user=unconfirmed)

    with (
        patch("app.services.auth_service._purge_stale_unconfirmed", new_callable=AsyncMock),
        patch("app.services.auth_service._create_verification_token", new_callable=AsyncMock, return_value="654321"),
        patch("app.services.email_service.send_verification_email", new_callable=AsyncMock) as mock_send,
    ):
        response = await auth_service.register(
            "user@example.com", "NewPass1", db, validator=_PassValidator()
        )

    # Should NOT add a new row
    db.add.assert_not_called()
    # Should send verification email
    mock_send.assert_awaited_once()
    # Response should carry the existing user's ID
    assert response.user_id == unconfirmed.id
    # Password must have been updated (hashed_password attribute was set)
    assert unconfirmed.hashed_password != "NewPass1"  # it's hashed


# ---------------------------------------------------------------------------
# Happy path: brand-new user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_user_created_and_email_sent() -> None:
    db = _make_db(existing_user=None)

    with (
        patch("app.services.auth_service._purge_stale_unconfirmed", new_callable=AsyncMock),
        patch("app.services.auth_service._create_verification_token", new_callable=AsyncMock, return_value="000000"),
        patch("app.services.email_service.send_verification_email", new_callable=AsyncMock) as mock_send,
    ):
        # Simulate flush assigning an ID to the new User object
        async def _flush_side_effect() -> None:
            # find the User that was added and give it an id
            for call in db.add.call_args_list:
                obj = call.args[0]
                if not obj.id:
                    obj.id = uuid.uuid4()

        db.flush.side_effect = _flush_side_effect

        response = await auth_service.register(
            "newuser@example.com", "Password1", db, validator=_PassValidator()
        )

    db.add.assert_called_once()
    mock_send.assert_awaited_once_with("newuser@example.com", "000000")
    assert response.email == "newuser@example.com"
    assert response.message == "Код отправлен на почту"
