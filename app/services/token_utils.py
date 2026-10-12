import hashlib
import secrets

from app.config import settings


def generate_code() -> str:
    # Dev stand only — Settings refuses it alongside a real email provider.
    if settings.DEV_FIXED_OTP_CODE:
        return settings.DEV_FIXED_OTP_CODE
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()
