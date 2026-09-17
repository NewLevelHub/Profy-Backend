import asyncio
import logging
from pathlib import Path

import resend

from app.config import settings
from app.i18n import DEFAULT_LOCALE, KNOWN_LOCALES
from app.i18n.catalog import tr

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "email"


def _email_locale(locale: str | None) -> str:
    """Clamp a recipient locale to one we actually ship email assets for.

    Unlike request-locale resolution (`app/i18n.get_locale()`), this honors
    ``kk`` before KZ-603: the source is the recipient's own stored choice
    (``users.locale``) or the registration ``Accept-Language`` — both already
    normalized through ``KNOWN_LOCALES`` on the write path (see
    ``app/routers/auth.py``). Anything else falls back to ``ru``.
    """
    return locale if locale in KNOWN_LOCALES else DEFAULT_LOCALE


def _load_template(name: str, locale: str, **kwargs: str) -> str:
    """Render the email body. ``name`` is the ``ru`` filename
    (``verification.html``); for a non-default locale, prefer the
    ``<stem>.<locale>.html`` sibling and fall back to the ``ru`` file if it is
    missing (contract §5 — never fail to a blank)."""
    path = _TEMPLATES_DIR / name
    if locale != DEFAULT_LOCALE:
        localized = path.with_suffix(f".{locale}.html")
        if localized.exists():
            path = localized
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


async def send_verification_email(
    to: str, code: str, *, locale: str = DEFAULT_LOCALE
) -> None:
    loc = _email_locale(locale)
    strings = tr("email", locale=loc)
    subject = strings["verification_subject"]
    plain = strings["verification_plain"].format(code=code)
    html = _load_template("verification.html", loc, code=code)

    if not settings.RESEND_API_KEY:
        logger.warning("Resend not configured — verification code for %s: %s", to, code)
        return

    try:
        await asyncio.to_thread(_send_resend, to, subject, plain, html)
    except Exception:
        logger.exception("Failed to send verification email to %s", to)
        raise


async def send_password_reset_email(
    to: str, code: str, *, locale: str = DEFAULT_LOCALE
) -> None:
    loc = _email_locale(locale)
    strings = tr("email", locale=loc)
    subject = strings["password_reset_subject"]
    plain = strings["password_reset_plain"].format(code=code)
    html = _load_template("password_reset.html", loc, code=code)

    if not settings.RESEND_API_KEY:
        logger.warning("Resend not configured — password reset code for %s: %s", to, code)
        return

    try:
        await asyncio.to_thread(_send_resend, to, subject, plain, html)
    except Exception:
        logger.exception("Failed to send password reset email to %s", to)
        raise
