import asyncio
import logging
from html import escape
from pathlib import Path

import resend

from app.config import settings

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "email"

# Best-effort notifications are awaited on request paths (report generation,
# publishing). Resend has no timeout of its own, so a hung provider would
# stall the student's request — cap it and move on. The worker thread may
# outlive the timeout; only the request stops waiting for it.
_BEST_EFFORT_TIMEOUT_SECONDS = 10


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
    subject = "Твой код подтверждения — Profile"
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


async def _send_best_effort(to: str, subject: str, plain: str, template: str, **kwargs: str) -> None:
    """Notification on a critical path (report generation, publishing) —
    unlike the OTP emails above, a failure here is logged and swallowed,
    never raised to the caller."""
    if not settings.RESEND_API_KEY:
        logger.warning("Resend not configured — skipping %s to %s", template, to)
        return
    try:
        html = _load_template(template, **{k: escape(v) for k, v in kwargs.items()})
        await asyncio.wait_for(
            asyncio.to_thread(_send_resend, to, subject, plain, html),
            timeout=_BEST_EFFORT_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.warning("%s to %s timed out after %ss", template, to, _BEST_EFFORT_TIMEOUT_SECONDS)
    except Exception:
        logger.exception("Failed to send %s to %s", template, to)


async def send_review_pending_email(to: str, student_name: str) -> None:
    """Психологу — новый отчёт ждёт проверки. Best-effort, никогда не raises."""
    await _send_best_effort(
        to,
        "Новый отчёт ждёт проверки — Profile",
        f"Ученик {student_name} завершил тест. Отчёт ждёт вашей проверки "
        "в разделе «Проверка отчётов» кабинета психолога.",
        "review_pending.html",
        student_name=student_name,
    )


async def send_result_published_email(to: str, student_name: str) -> None:
    """Ученику — результат опубликован. Best-effort, никогда не raises."""
    await _send_best_effort(
        to,
        "Твой результат готов — Profile",
        f"{student_name}, психолог проверил твой отчёт — он уже ждёт тебя в Profile.",
        "result_published.html",
        student_name=student_name,
    )


async def send_password_reset_email(to: str, code: str) -> None:
    subject = "Сброс пароля — Profile"
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
