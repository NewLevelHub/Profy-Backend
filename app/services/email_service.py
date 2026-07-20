import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_SMTP_TIMEOUT = 10
_TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "email"


def _load_template(name: str, **kwargs: str) -> str:
    path = _TEMPLATES_DIR / name
    return path.read_text(encoding="utf-8").format(**kwargs)


def _sender_domain() -> str:
    _, _, domain = settings.EMAIL_FROM.rpartition("@")
    return domain or "localhost"


def _send_smtp(to: str, subject: str, plain: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((settings.EMAIL_FROM_NAME or "", settings.EMAIL_FROM))
    msg["To"] = to
    # Date and a domain-scoped Message-ID are expected by receivers; missing
    # them is a common reason transactional mail is flagged as spam.
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=_sender_domain())
    if settings.EMAIL_REPLY_TO:
        msg["Reply-To"] = settings.EMAIL_REPLY_TO
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    use_ssl = settings.SMTP_PORT == 465
    if use_ssl:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=_SMTP_TIMEOUT) as server:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.EMAIL_FROM, to, msg.as_string())
    else:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=_SMTP_TIMEOUT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()  # re-identify after TLS handshake
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.EMAIL_FROM, to, msg.as_string())


async def send_verification_email(to: str, code: str) -> None:
    subject = "Твой код подтверждения — Profy"
    plain = f"Твой код подтверждения: {code}\n\nКод действителен 15 минут."
    html = _load_template("verification.html", code=code)

    if not settings.SMTP_HOST:
        logger.warning("SMTP not configured — verification code for %s: %s", to, code)
        return

    try:
        await asyncio.to_thread(_send_smtp, to, subject, plain, html)
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

    if not settings.SMTP_HOST:
        logger.warning("SMTP not configured — password reset code for %s: %s", to, code)
        return

    try:
        await asyncio.to_thread(_send_smtp, to, subject, plain, html)
    except Exception:
        logger.exception("Failed to send password reset email to %s", to)
        raise
