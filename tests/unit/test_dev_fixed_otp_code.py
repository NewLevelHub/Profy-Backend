"""DEV_FIXED_OTP_CODE: a fixed verification/reset code for the dev stand.
It lets anyone who knows it verify any email or reset any password, so the
Settings guard against a real email provider is the part that matters."""

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.services import auth_service, email_service
from app.services.token_utils import generate_code

_REQUIRED = {"REDIS_URL": "redis://redis:6379/0", "SECRET_KEY": "x", "DATABASE_URL": "postgresql+asyncpg://u:p@db/d"}


def _settings(**overrides: str) -> Settings:
    # Provider keys explicitly empty: the test container's own env may set them.
    return Settings(
        _env_file=None,
        **{**_REQUIRED, "RESEND_API_KEY": "", "SES_ACCESS_KEY_ID": "", **overrides},
    )


@pytest.mark.parametrize(
    "provider_credentials",
    [
        {"RESEND_API_KEY": "re_live_key"},
        # Refused even while Resend is the selected provider: switching
        # EMAIL_PROVIDER later must not turn the fixed code live.
        {"SES_ACCESS_KEY_ID": "AKIATEST"},
    ],
)
def test_fixed_code_is_refused_with_a_real_email_provider(provider_credentials: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="must not be set together"):
        _settings(DEV_FIXED_OTP_CODE="000000", **provider_credentials)


@pytest.mark.parametrize("code", ["00000", "0000000", "abcdef", "12 456"])
def test_fixed_code_must_be_six_digits(code: str) -> None:
    with pytest.raises(ValidationError, match="6 digits"):
        _settings(DEV_FIXED_OTP_CODE=code)


def test_fixed_code_alone_is_accepted() -> None:
    assert _settings(DEV_FIXED_OTP_CODE="000000").DEV_FIXED_OTP_CODE == "000000"


def test_codes_are_random_without_the_setting(monkeypatch) -> None:
    monkeypatch.setattr(settings, "DEV_FIXED_OTP_CODE", "")
    codes = {generate_code() for _ in range(50)}
    assert len(codes) > 1
    assert all(len(c) == 6 and c.isdigit() for c in codes)


async def test_register_then_verify_with_the_fixed_code(db_session: AsyncSession, monkeypatch) -> None:
    async def _no_send(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(settings, "DEV_FIXED_OTP_CODE", "000000")
    monkeypatch.setattr(email_service, "send_verification_email", _no_send)

    email = f"{uuid.uuid4()}@example.test"
    await auth_service.register(email, "Testpass123!", db_session)
    user, token = await auth_service.verify_email(email, "000000", db_session)

    assert user.is_verified is True
    assert token
