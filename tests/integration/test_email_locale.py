"""KZ-308 — verification / password-reset emails follow the recipient's locale.

`email_service` only logs the code when `RESEND_API_KEY` is unset (see the Resend
migration note), so these tests set a dummy key and stub `_send_resend` to
capture the rendered subject / plain / html, then assert on their content and on
which template file was picked.
"""

import uuid

import pytest

from app.services import auth_service, email_service, password_reset_service
from app.models.user import User


@pytest.fixture
def sent(monkeypatch):
    captured: list[dict[str, str]] = []

    def _capture(to: str, subject: str, plain: str, html: str) -> None:
        captured.append({"to": to, "subject": subject, "plain": plain, "html": html})

    monkeypatch.setattr(email_service.settings, "RESEND_API_KEY", "test-key")
    monkeypatch.setattr(email_service, "_send_resend", _capture)
    return captured


async def test_verification_email_kk_body_and_subject(sent) -> None:
    await email_service.send_verification_email("u@example.com", "123456", locale="kk")

    msg = sent[0]
    assert msg["subject"] == "Растау кодың — Profy"
    assert msg["plain"] == "Растау кодың: 123456\n\nКод 15 минут жарамды."
    assert 'lang="kk"' in msg["html"]
    assert "Поштаңды раста" in msg["html"]
    assert "123456" in msg["html"]


async def test_verification_email_ru_is_byte_for_byte_unchanged(sent) -> None:
    await email_service.send_verification_email("u@example.com", "123456", locale="ru")

    msg = sent[0]
    assert msg["subject"] == "Твой код подтверждения — Profy"
    assert msg["plain"] == "Твой код подтверждения: 123456\n\nКод действителен 15 минут."
    assert 'lang="ru"' in msg["html"]
    assert "Подтверди почту" in msg["html"]


async def test_password_reset_email_kk_body_and_subject(sent) -> None:
    await email_service.send_password_reset_email("u@example.com", "654321", locale="kk")

    msg = sent[0]
    assert msg["subject"] == "Құпиясөзді қалпына келтіру — Profy"
    assert "Құпиясөзді қалпына келтіру кодың: 654321" in msg["plain"]
    assert "бұл хатты елемей қой" in msg["plain"]
    assert 'lang="kk"' in msg["html"]
    assert "Қалпына келтіруді сұрамадың ба?" in msg["html"]


async def test_password_reset_email_ru_unchanged(sent) -> None:
    await email_service.send_password_reset_email("u@example.com", "654321", locale="ru")

    msg = sent[0]
    assert msg["subject"] == "Сброс пароля — Profy"
    assert msg["plain"] == (
        "Твой код для сброса пароля: 654321\n\n"
        "Код действителен 15 минут.\n\n"
        "Если ты не запрашивал сброс пароля — проигнорируй это письмо."
    )
    assert 'lang="ru"' in msg["html"]


async def test_unknown_or_missing_locale_falls_back_to_ru(sent) -> None:
    await email_service.send_verification_email("u@example.com", "111111", locale="de")
    await email_service.send_verification_email("u@example.com", "222222", locale=None)

    assert sent[0]["subject"] == "Твой код подтверждения — Profy"
    assert sent[1]["subject"] == "Твой код подтверждения — Profy"


async def test_registration_with_accept_language_kk_sends_kk_verification(
    sent, db_session
) -> None:
    email = f"{uuid.uuid4()}@example.com"
    await auth_service.register(email, "Testpass123!", db_session, locale="kk")

    assert sent, "no verification email was captured"
    assert sent[0]["subject"] == "Растау кодың — Profy"
    assert 'lang="kk"' in sent[0]["html"]


async def test_password_reset_uses_the_stored_account_locale(sent, db_session) -> None:
    email = f"{uuid.uuid4()}@example.com"
    db_session.add(
        User(
            email=email,
            hashed_password=auth_service.hash_password("Testpass123!"),
            is_active=True,
            is_verified=True,
            locale="kk",
        )
    )
    await db_session.commit()

    await password_reset_service.initiate_reset(email, db_session)

    assert sent, "no password-reset email was captured"
    assert sent[0]["subject"] == "Құпиясөзді қалпына келтіру — Profy"
