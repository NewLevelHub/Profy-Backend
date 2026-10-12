"""EMAIL_PROVIDER switch: the same email_service entry points send through
Resend or Amazon SES, picked by one setting. SES is checked against the real
sesv2 request schema with botocore's Stubber — no network."""

import pytest
from botocore.stub import Stubber

from app.config import Settings
from app.services import email_service

_REQUIRED = {"REDIS_URL": "redis://redis:6379/0", "SECRET_KEY": "x", "DATABASE_URL": "postgresql+asyncpg://u:p@db/d"}


@pytest.fixture
def ses(monkeypatch):
    """Select SES with dummy credentials and stub its client."""
    for name, value in {
        "EMAIL_PROVIDER": "ses",
        "SES_REGION": "ap-southeast-2",
        "SES_ACCESS_KEY_ID": "AKIATEST",
        "SES_SECRET_ACCESS_KEY": "secret",
        "EMAIL_FROM": "Profy <verify@newlevelhub.kz>",
    }.items():
        monkeypatch.setattr(email_service.settings, name, value)
    email_service._ses_client.cache_clear()
    client = email_service._ses_client()
    with Stubber(client) as stubber:
        yield stubber
    email_service._ses_client.cache_clear()


async def test_verification_email_goes_through_ses(ses, monkeypatch) -> None:
    def _no_resend(*args, **kwargs):
        raise AssertionError("Resend must not be called when EMAIL_PROVIDER=ses")

    monkeypatch.setattr(email_service, "_send_resend", _no_resend)
    ses.add_response("send_email", {"MessageId": "ses-message-1"})

    await email_service.send_verification_email("student@example.test", "123456", locale="ru")

    ses.assert_no_pending_responses()


async def test_ses_request_carries_subject_text_and_html(ses) -> None:
    captured = {}
    ses.add_response("send_email", {"MessageId": "ses-message-2"})
    client = email_service._ses_client()
    client.meta.events.register(
        "provide-client-params.sesv2.SendEmail", lambda params, **kw: captured.update(params)
    )

    message_id = await email_service.send_invitation_email(
        "staff@example.test", "https://profile.test/invite/abc", role=email_service.UserRole.psychologist, locale="kk"
    )

    assert message_id == "ses-message-2"
    assert captured["FromEmailAddress"] == "Profy <verify@newlevelhub.kz>"
    assert captured["Destination"] == {"ToAddresses": ["staff@example.test"]}
    body = captured["Content"]["Simple"]
    assert body["Subject"]["Charset"] == "UTF-8" and body["Subject"]["Data"]
    assert "https://profile.test/invite/abc" in body["Body"]["Text"]["Data"]
    assert "https://profile.test/invite/abc" in body["Body"]["Html"]["Data"]


async def test_ses_failure_raises_for_otp_emails(ses) -> None:
    ses.add_client_error("send_email", service_error_code="MessageRejected", http_status_code=400)

    with pytest.raises(Exception, match="MessageRejected"):
        await email_service.send_password_reset_email("student@example.test", "123456")


def test_resend_stays_the_default_provider(monkeypatch) -> None:
    captured = []
    monkeypatch.setattr(email_service.settings, "EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(email_service, "_send_resend", lambda *a: captured.append(a) or "re-1")
    monkeypatch.setattr(email_service, "_send_ses", lambda *a: pytest.fail("SES must not be called"))

    assert email_service._send("a@example.test", "s", "p", "<p>h</p>") == "re-1"
    assert captured


@pytest.mark.parametrize(
    "overrides, configured",
    [
        ({"EMAIL_PROVIDER": "resend", "RESEND_API_KEY": "re_key"}, True),
        ({"EMAIL_PROVIDER": "resend", "RESEND_API_KEY": "", "SES_ACCESS_KEY_ID": "AKIA"}, False),
        (
            {"EMAIL_PROVIDER": "ses", "SES_REGION": "ap-southeast-2", "SES_ACCESS_KEY_ID": "AKIA", "SES_SECRET_ACCESS_KEY": "s"},
            True,
        ),
        ({"EMAIL_PROVIDER": "ses", "RESEND_API_KEY": "re_key", "SES_REGION": "ap-southeast-2"}, False),
    ],
)
def test_configured_means_the_selected_provider_can_send(overrides: dict, configured: bool) -> None:
    base = {"RESEND_API_KEY": "", "SES_REGION": "", "SES_ACCESS_KEY_ID": "", "SES_SECRET_ACCESS_KEY": ""}
    settings = Settings(_env_file=None, **{**_REQUIRED, **base, **overrides})
    assert settings.email_delivery_configured is configured


def test_unknown_provider_is_refused() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, **_REQUIRED, EMAIL_PROVIDER="mailgun")
