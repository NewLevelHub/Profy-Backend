"""Secrets stay out of the logs (SEC-08).

The invitation token travels in a request body and a URL fragment, never in
a path or query an access log would record. Emailed codes are written to the
log only on a stack that asked for it with `LOG_EMAIL_CODES` (local
development); anywhere else a missing `RESEND_API_KEY` is a failed send.
"""

import logging
import uuid

import pytest
from sqlalchemy import select

from app.config import Settings
from app.models.user import User
from app.services import auth_service, email_service, password_reset_service

CODE = "424242"
SENDERS = [email_service.send_verification_email, email_service.send_password_reset_email]


@pytest.fixture
def no_provider(monkeypatch):
    def _fail(*_args) -> None:
        raise AssertionError("must not send without RESEND_API_KEY")

    monkeypatch.setattr(email_service.settings, "RESEND_API_KEY", "")
    monkeypatch.setattr(email_service, "_send_resend", _fail)


def _everything_logged(caplog) -> str:
    # Messages and tracebacks: a code must not surface through either.
    return caplog.text


def test_code_logging_is_off_unless_a_stack_turns_it_on():
    assert Settings.model_fields["LOG_EMAIL_CODES"].default is False


@pytest.mark.parametrize("send", SENDERS)
async def test_without_a_provider_the_code_is_never_logged_by_default(send, no_provider, monkeypatch, caplog):
    monkeypatch.setattr(email_service.settings, "LOG_EMAIL_CODES", False)

    with caplog.at_level(logging.DEBUG, logger="app"), pytest.raises(RuntimeError, match="RESEND_API_KEY"):
        await send("student@example.com", CODE)

    assert CODE not in _everything_logged(caplog)


@pytest.mark.parametrize("send", SENDERS)
async def test_local_stack_gets_the_code_in_the_log(send, no_provider, monkeypatch, caplog):
    monkeypatch.setattr(email_service.settings, "LOG_EMAIL_CODES", True)

    with caplog.at_level(logging.DEBUG, logger="app"):
        await send("student@example.com", CODE)

    assert CODE in _everything_logged(caplog)


@pytest.mark.parametrize("send", SENDERS)
async def test_with_a_provider_the_flag_logs_nothing(send, monkeypatch, caplog):
    sent = []
    monkeypatch.setattr(email_service.settings, "RESEND_API_KEY", "test-key")
    monkeypatch.setattr(email_service.settings, "LOG_EMAIL_CODES", True)
    monkeypatch.setattr(email_service, "_send_resend", lambda *args: sent.append(args) or "id")

    with caplog.at_level(logging.DEBUG, logger="app"):
        await send("student@example.com", CODE)

    assert len(sent) == 1
    assert CODE not in _everything_logged(caplog)


@pytest.mark.parametrize("send", SENDERS)
async def test_the_flag_follows_the_selected_provider_not_the_resend_key(send, monkeypatch, caplog):
    """SES selected and configured, no Resend key at all: the email is sent.
    Reading `RESEND_API_KEY` here would stop every code email on such a stack."""
    sent = []
    for name, value in {
        "EMAIL_PROVIDER": "ses",
        "SES_REGION": "ap-southeast-2",
        "SES_ACCESS_KEY_ID": "AKIATEST",
        "SES_SECRET_ACCESS_KEY": "secret",
        "RESEND_API_KEY": "",
        "LOG_EMAIL_CODES": False,
    }.items():
        monkeypatch.setattr(email_service.settings, name, value)
    monkeypatch.setattr(email_service, "_send_ses", lambda *args: sent.append(args) or "id")

    with caplog.at_level(logging.DEBUG, logger="app"):
        await send("student@example.com", CODE)

    assert len(sent) == 1
    assert CODE not in _everything_logged(caplog)


@pytest.mark.parametrize("send", SENDERS)
async def test_unconfigured_ses_is_reported_by_its_own_settings(send, monkeypatch, caplog):
    for name, value in {
        "EMAIL_PROVIDER": "ses",
        "SES_REGION": "",
        "SES_ACCESS_KEY_ID": "",
        "SES_SECRET_ACCESS_KEY": "",
        # A leftover Resend key must not count for the provider that is selected.
        "RESEND_API_KEY": "test-key",
        "LOG_EMAIL_CODES": False,
    }.items():
        monkeypatch.setattr(email_service.settings, name, value)

    with caplog.at_level(logging.DEBUG, logger="app"), pytest.raises(RuntimeError, match="SES_ACCESS_KEY_ID"):
        await send("student@example.com", CODE)

    assert CODE not in _everything_logged(caplog)


@pytest.mark.parametrize("send", SENDERS)
async def test_dev_stand_with_a_fixed_code_sends_and_logs_nothing(send, no_provider, monkeypatch, caplog):
    """The fixed code is how a tester of the dev stand gets in — there is no
    email to send, and it is not an error either."""
    monkeypatch.setattr(email_service.settings, "LOG_EMAIL_CODES", False)
    monkeypatch.setattr(email_service.settings, "DEV_FIXED_OTP_CODE", "000000")

    with caplog.at_level(logging.DEBUG, logger="app"):
        await send("student@example.com", "000000")

    assert "000000" not in _everything_logged(caplog)


async def test_registration_on_a_misconfigured_server_reports_the_failure_without_the_code(
    db_session, no_provider, monkeypatch, caplog
):
    monkeypatch.setattr(email_service.settings, "LOG_EMAIL_CODES", False)
    monkeypatch.setattr(auth_service, "generate_code", lambda: CODE)
    email = f"{uuid.uuid4()}@example.com"

    with caplog.at_level(logging.DEBUG, logger="app"):
        response = await auth_service.register(email, "Testpass123!", db_session)

    # The account exists; the operator sees why no email went out.
    assert response.email == email
    assert await db_session.scalar(select(User).where(User.email == email)) is not None
    logged = _everything_logged(caplog)
    assert "RESEND_API_KEY is not configured" in logged
    assert CODE not in logged


async def test_password_reset_on_a_misconfigured_server_reports_the_failure_without_the_code(
    db_session, no_provider, monkeypatch, caplog
):
    monkeypatch.setattr(email_service.settings, "LOG_EMAIL_CODES", False)
    monkeypatch.setattr(password_reset_service, "generate_code", lambda: CODE)
    user = User(
        email=f"{uuid.uuid4()}@example.com",
        hashed_password=auth_service.hash_password("Testpass123!"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()

    with caplog.at_level(logging.DEBUG, logger="app"):
        await password_reset_service.initiate_reset(user.email, db_session)

    logged = _everything_logged(caplog)
    assert "RESEND_API_KEY is not configured" in logged
    assert CODE not in logged


async def test_no_route_takes_the_invitation_token_in_its_path(client):
    token = "not-a-real-token"

    response = await client.get(f"/api/v1/auth/invitations/{token}")

    assert response.status_code in (404, 405)
