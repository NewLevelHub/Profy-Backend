import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from app.config import settings
from app.models.email_verification import EmailVerificationToken
from app.models.password_reset import PasswordResetToken

# Wrong guesses one emailed code survives. A six-digit code has only 10^6
# values, so the budget belongs to the code itself: a counter keyed by
# anything the caller controls (endpoint, IP) can be sidestepped.
MAX_CODE_ATTEMPTS = 5


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str) -> str:
    """Keyed hash of a short one-time code. A bare SHA-256 of six digits is
    reversed from a database dump by trying every value; this also needs
    `SECRET_KEY`, which is not in the database."""
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), code.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def code_matches(code_hash: str, code: str) -> bool:
    return hmac.compare_digest(code_hash, hash_code(code))


def record_failed_attempt(token: PasswordResetToken | EmailVerificationToken) -> None:
    """Spend one guess; the last one burns the code. The caller holds the row
    lock and commits, so parallel guesses are counted one by one."""
    token.attempts += 1
    if token.attempts >= MAX_CODE_ATTEMPTS:
        token.used_at = datetime.now(timezone.utc)
