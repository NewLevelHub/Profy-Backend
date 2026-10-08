"""PRO-461 — staff invitation email: ru/kk rendering and the dev-only
"no RESEND_API_KEY → link goes to the log" path."""

import logging

import pytest

from app.models.user import UserRole
from app.services import email_service

INVITE_URL = "https://profile.example.com/invite?token=Abc-123_xyz"


@pytest.fixture
def sent(monkeypatch):
    captured: list[dict[str, str]] = []

    def _capture(to: str, subject: str, plain: str, html: str) -> str:
        captured.append({"to": to, "subject": subject, "plain": plain, "html": html})
        return "resend-message-id"

    monkeypatch.setattr(email_service.settings, "RESEND_API_KEY", "test-key")
    monkeypatch.setattr(email_service.settings, "INVITATION_TTL_HOURS", 72)
    monkeypatch.setattr(email_service, "_send_resend", _capture)
    return captured


async def test_ru_invitation_has_role_ttl_and_link(sent) -> None:
    await email_service.send_invitation_email(
        "psy@example.com", INVITE_URL, role=UserRole.psychologist, locale="ru"
    )

    msg = sent[0]
    assert msg["to"] == "psy@example.com"
    assert msg["subject"] == "Приглашение в Profile"
    assert "в роли психолога" in msg["plain"]
    assert "72 ч." in msg["plain"]
    assert INVITE_URL in msg["plain"]
    assert 'lang="ru"' in msg["html"]
    assert "в роли психолога" in msg["html"]
    assert f'href="{INVITE_URL}"' in msg["html"]
    assert "Принять приглашение" in msg["html"]
    assert "72&nbsp;ч." in msg["html"]


@pytest.mark.parametrize("locale", ["ru", "kk"])
async def test_html_has_only_the_button_not_the_raw_link(sent, locale: str) -> None:
    """The plain-text part keeps the URL; the HTML part shows just the button."""
    await email_service.send_invitation_email(
        "psy@example.com", INVITE_URL, role=UserRole.psychologist, locale=locale
    )

    assert sent[0]["html"].count(INVITE_URL) == 1


async def test_kk_invitation_has_role_ttl_and_link(sent) -> None:
    await email_service.send_invitation_email(
        "admin@example.com", INVITE_URL, role=UserRole.admin, locale="kk"
    )

    msg = sent[0]
    assert msg["subject"] == "Profile платформасына шақыру"
    assert "әкімші ретінде" in msg["plain"]
    assert "72 сағат" in msg["plain"]
    assert INVITE_URL in msg["plain"]
    assert 'lang="kk"' in msg["html"]
    assert "әкімші ретінде" in msg["html"]
    assert f'href="{INVITE_URL}"' in msg["html"]
    assert "Шақыруды қабылдау" in msg["html"]


async def test_unknown_locale_falls_back_to_ru(sent) -> None:
    await email_service.send_invitation_email(
        "psy@example.com", INVITE_URL, role=UserRole.psychologist, locale="de"
    )

    assert sent[0]["subject"] == "Приглашение в Profile"
    assert 'lang="ru"' in sent[0]["html"]


async def test_url_is_html_escaped_in_html_but_not_in_plain(sent) -> None:
    url = "https://profile.example.com/invite?token=a&b=<c>"
    await email_service.send_invitation_email(
        "psy@example.com", url, role=UserRole.psychologist, locale="ru"
    )

    msg = sent[0]
    assert url in msg["plain"]
    assert "token=a&amp;b=&lt;c&gt;" in msg["html"]
    assert "<c>" not in msg["html"]


async def test_without_resend_key_nothing_is_sent_and_link_is_not_logged(monkeypatch, caplog) -> None:
    def _fail(*_args) -> None:
        raise AssertionError("must not send without RESEND_API_KEY")

    monkeypatch.setattr(email_service.settings, "RESEND_API_KEY", "")
    monkeypatch.setattr(email_service, "_send_resend", _fail)

    with caplog.at_level(logging.DEBUG, logger=email_service.logger.name):
        message_id = await email_service.send_invitation_email(
            "psy@example.com", INVITE_URL, role=UserRole.psychologist, locale="ru"
        )

    assert message_id is None
    # The link is a bearer credential for a staff account — never in logs.
    assert "token=" not in caplog.text
    assert "psy@example.com" in caplog.text


async def test_successful_send_returns_the_resend_id(sent) -> None:
    message_id = await email_service.send_invitation_email(
        "psy@example.com", INVITE_URL, role=UserRole.psychologist, locale="ru"
    )

    assert message_id == "resend-message-id"
    assert len(sent) == 1


async def test_provider_failure_is_raised(monkeypatch) -> None:
    def _boom(*_args) -> None:
        raise RuntimeError("resend down")

    monkeypatch.setattr(email_service.settings, "RESEND_API_KEY", "test-key")
    monkeypatch.setattr(email_service, "_send_resend", _boom)

    with pytest.raises(RuntimeError):
        await email_service.send_invitation_email(
            "psy@example.com", INVITE_URL, role=UserRole.psychologist, locale="ru"
        )
