import asyncio
import logging
from pathlib import Path

import resend

from app.config import settings

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "email"


def _load_template(name: str, **kwargs: str) -> str:
    path = _TEMPLATES_DIR / name
    return path.read_text(encoding="utf-8").format(**kwargs)


def _send_resend(to: str, subject: str, plain: str, html: str) -> None:
    resend.api_key = settings.RESEND_API_KEY
    resend.Emails.send(
        {
            "from": settings.EMAIL_FROM,
            "to": [to],
            "subject": subject,
            "html": html,
            "text": plain,
        }
    )


async def send_verification_email(to: str, code: str) -> None:
    subject = "Твой код подтверждения — Profy"
    plain = f"Твой код подтверждения: {code}\n\nКод действителен 15 минут."
    html = _load_template("verification.html", code=code)

    if not settings.RESEND_API_KEY:
        logger.warning("Resend not configured — verification code for %s: %s", to, code)
        return

    try:
        await asyncio.to_thread(_send_resend, to, subject, plain, html)
    except Exception:
        logger.exception("Failed to send verification email to %s", to)
        raise


async def send_password_reset_email(to: str, code: str) -> None:
    subject = "Сброс пароля — Profy"
    plain = (
        f"Твой код для сброса пароля: {code}\n\n"
        "Код действителен 15 минут.\n\n"
        "Если ты не запрашивал сброс пароля — проигнорируй это письмо."
    )
    html = _load_template("password_reset.html", code=code)

    if not settings.RESEND_API_KEY:
        logger.warning("Resend not configured — password reset code for %s: %s", to, code)
        return

    try:
        await asyncio.to_thread(_send_resend, to, subject, plain, html)
    except Exception:
        logger.exception("Failed to send password reset email to %s", to)
        raise
