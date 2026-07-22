"""
Unit tests for app/services/email_validator.py
"""

from unittest.mock import patch

import dns.exception
import dns.resolver
import pytest
from fastapi import HTTPException

from app.services.email_validator import MXRecordEmailValidator, _MX_ERROR_MSG


@pytest.fixture()
def validator() -> MXRecordEmailValidator:
    return MXRecordEmailValidator()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_domain_passes(validator: MXRecordEmailValidator) -> None:
    """MX records found — no exception raised."""
    with patch("app.services.email_validator.dns.resolver.resolve", return_value=["mx1"]):
        await validator.validate("user@example.com")  # must not raise


# ---------------------------------------------------------------------------
# Rejection cases — every DNS failure mode maps to HTTP 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc_cls",
    [
        dns.resolver.NXDOMAIN,
        dns.resolver.NoAnswer,
        dns.resolver.NoNameservers,
    ],
)
async def test_dns_error_raises_422(
    validator: MXRecordEmailValidator, exc_cls: type
) -> None:
    with patch(
        "app.services.email_validator.dns.resolver.resolve",
        side_effect=exc_cls(),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await validator.validate("user@no-such-domain.xyz")

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == _MX_ERROR_MSG


@pytest.mark.asyncio
async def test_timeout_raises_422(validator: MXRecordEmailValidator) -> None:
    with patch(
        "app.services.email_validator.dns.resolver.resolve",
        side_effect=dns.exception.Timeout(),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await validator.validate("user@slow-domain.xyz")

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == _MX_ERROR_MSG


# ---------------------------------------------------------------------------
# Unexpected DNS errors should NOT block registration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unexpected_dns_error_does_not_raise(
    validator: MXRecordEmailValidator,
) -> None:
    """An unanticipated exception from the DNS library must be swallowed."""
    with patch(
        "app.services.email_validator.dns.resolver.resolve",
        side_effect=RuntimeError("unexpected"),
    ):
        await validator.validate("user@example.com")  # must not raise


# ---------------------------------------------------------------------------
# Domain extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subdomain_extracted_correctly(validator: MXRecordEmailValidator) -> None:
    captured: list[str] = []

    def _fake_resolve(domain: str, record_type: str) -> list:
        captured.append(domain)
        return ["mx1"]

    with patch("app.services.email_validator.dns.resolver.resolve", side_effect=_fake_resolve):
        await validator.validate("user@mail.sub.example.com")

    assert captured == ["mail.sub.example.com"]
