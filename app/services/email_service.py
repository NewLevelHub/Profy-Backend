import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from html import escape
from pathlib import Path

import resend

from app.config import settings
from app.i18n import DEFAULT_LOCALE, KNOWN_LOCALES
from app.i18n.catalog import tr

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "email"

# Best-effort notifications are awaited on request paths (report generation,
# publishing) — a slow provider must not stall the student's request, so the
# wait is capped (and the HTTP call itself is capped to match, below).
_BEST_EFFORT_TIMEOUT_SECONDS = 10

# `asyncio.wait_for` only stops the *waiting*: the blocking Resend call keeps
# its thread until the provider answers. On the shared default executor those
# stuck threads would eventually starve every other `to_thread` user (OAuth
# verification, artifact uploads), so notifications get their own small pool.
_EMAIL_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="email-send")

# `wait_for` above caps how long the request waits, not the HTTP call itself:
# the library's own client defaults to 30s, so a stuck send kept its worker
# long after we gave up — and `concurrent.futures`' atexit hook joins those
# workers, delaying container shutdown on deploy. Align the two.
try:
    from resend.http_client_requests import RequestsClient

    resend.default_http_client = RequestsClient(timeout=_BEST_EFFORT_TIMEOUT_SECONDS)
except Exception:  # library layout changed — its own 30s default still applies
    logger.warning("could not set the Resend HTTP timeout — falling back to the library default")


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


async def _send_best_effort(
    to: str, subject: str, plain: str, template: str, *, locale: str = DEFAULT_LOCALE, **kwargs: str
) -> None:
    """Notification on a critical path (report generation, publishing) —
    unlike the OTP emails, a failure here is logged and swallowed, never
    raised to the caller."""
    if not settings.RESEND_API_KEY:
        logger.warning("Resend not configured — skipping %s to %s", template, to)
        return
    try:
        html = _load_template(
            template, _email_locale(locale), **{k: escape(v) for k, v in kwargs.items()}
        )
        loop = asyncio.get_running_loop()
        await asyncio.wait_for(
            loop.run_in_executor(_EMAIL_EXECUTOR, _send_resend, to, subject, plain, html),
            timeout=_BEST_EFFORT_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.warning("%s to %s timed out after %ss", template, to, _BEST_EFFORT_TIMEOUT_SECONDS)
    except Exception:
        logger.exception("Failed to send %s to %s", template, to)


async def send_review_pending_email(to: str, student_name: str) -> None:
    """Психологу — новый отчёт ждёт проверки. Кабинет психолога только на
    русском (KZ-210), поэтому и это письмо всегда ru. Best-effort, никогда не raises."""
    strings = tr("email", locale=DEFAULT_LOCALE)
    await _send_best_effort(
        to,
        strings["review_pending_subject"],
        strings["review_pending_plain"].format(student_name=student_name),
        "review_pending.html",
        student_name=student_name,
    )


async def send_result_published_email(
    to: str, student_name: str | None, *, locale: str = DEFAULT_LOCALE
) -> None:
    """Ученику — результат опубликован, на языке ученика (`users.locale`).
    Best-effort, никогда не raises."""
    loc = _email_locale(locale)
    strings = tr("email", locale=loc)
    name = student_name or strings["result_published_fallback_name"]
    await _send_best_effort(
        to,
        strings["result_published_subject"],
        strings["result_published_plain"].format(student_name=name),
        "result_published.html",
        locale=loc,
        student_name=name,
    )


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
