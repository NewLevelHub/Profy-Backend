import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_SMTP_TIMEOUT = 10
_TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "email"


def _load_template(name: str, **kwargs: str) -> str:
    path = _TEMPLATES_DIR / name
    return path.read_text(encoding="utf-8").format(**kwargs)


def _send_smtp(to: str, subject: str, plain: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=_SMTP_TIMEOUT) as server:
        server.ehlo()
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.EMAIL_FROM, to, msg.as_string())


async def send_verification_email(to: str, code: str) -> None:
    subject = "Твой код подтверждения — Profy"
    plain = f"Твой код подтверждения: {code}\n\nКод действителен 15 минут."
    html = _load_template("verification.html", code=code)

    if not settings.SMTP_HOST:
        logger.warning("SMTP not configured — verification code for %s: %s", to, code)
        return

    await asyncio.to_thread(_send_smtp, to, subject, plain, html)


async def send_password_reset_email(to: str, code: str) -> None:
    subject = "Сброс пароля — Profy"
    plain = (
        f"Твой код для сброса пароля: {code}\n\n"
        "Код действителен 15 минут.\n\n"
        "Если ты не запрашивал сброс пароля — проигнорируй это письмо."
    )
    html = _load_template("password_reset.html", code=code)

    if not settings.SMTP_HOST:
        logger.warning("SMTP not configured — password reset code for %s: %s", to, code)
        return

    await asyncio.to_thread(_send_smtp, to, subject, plain, html)
