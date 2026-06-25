import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)


def _send_smtp(to: str, subject: str, body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.EMAIL_FROM, to, msg.as_string())


async def send_verification_email(to: str, code: str) -> None:
    subject = "Ваш код подтверждения"
    body = f"Ваш код подтверждения: {code}\n\nКод действителен 15 минут."

    if not settings.SMTP_HOST:
        logger.warning("SMTP not configured — verification code for %s: %s", to, code)
        return

    await asyncio.to_thread(_send_smtp, to, subject, body)


async def send_password_reset_email(to: str, code: str) -> None:
    subject = "Код подтверждения"
    body = f"Ваш код для сброса пароля: {code}\n\nКод действителен 15 минут.\n\nЕсли вы не запрашивали сброс пароля — проигнорируйте это письмо."

    if not settings.SMTP_HOST:
        logger.warning("SMTP not configured — password reset code for %s: %s", to, code)
        return

    await asyncio.to_thread(_send_smtp, to, subject, body)
