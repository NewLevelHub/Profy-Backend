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

    def _capture(to: str, subject: str, plain: str, html: str) -> None:
        captured.append({"to": to, "subject": subject, "plain": plain, "html": html})

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


async def test_without_resend_key_link_is_logged_and_nothing_sent(monkeypatch, caplog) -> None:
    def _fail(*_args) -> None:
        raise AssertionError("must not send without RESEND_API_KEY")

    monkeypatch.setattr(email_service.settings, "RESEND_API_KEY", "")
    monkeypatch.setattr(email_service, "_send_resend", _fail)

    with caplog.at_level(logging.WARNING, logger=email_service.logger.name):
        await email_service.send_invitation_email(
            "psy@example.com", INVITE_URL, role=UserRole.psychologist, locale="ru"
        )

    assert INVITE_URL in caplog.text


async def test_provider_failure_is_raised(monkeypatch) -> None:
    def _boom(*_args) -> None:
        raise RuntimeError("resend down")

    monkeypatch.setattr(email_service.settings, "RESEND_API_KEY", "test-key")
    monkeypatch.setattr(email_service, "_send_resend", _boom)

    with pytest.raises(RuntimeError):
        await email_service.send_invitation_email(
            "psy@example.com", INVITE_URL, role=UserRole.psychologist, locale="ru"
        )
