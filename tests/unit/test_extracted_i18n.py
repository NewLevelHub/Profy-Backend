"""Regression checks for extracted copy, locale resolution and stable API errors."""

from string import Formatter
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.i18n import use_locale
from app.i18n.catalog import _AREAS, api_errors
from app.main import app
from app.routers import auth
from app.schemas.auth import RegisterRequest, UpdateMeRequest
from app.schemas.certificate import CertificateItem
from app.services import auth_service, ipsative_battery
from app.services.astur.bank import load_v1_document, parse_bank
from app.services.astur.runs import _subtest_or_404


@pytest.mark.parametrize(
    "area",
    ["api_errors", "api_messages", "admin_export", "report_copy", "riasec_explanations"],
)
def test_extracted_templates_preserve_placeholders_in_both_locales(area):
    module = _AREAS[area]
    formatter = Formatter()
    for name, ru in module.RU.items():
        kk = module.KK[name]
        assert ru.strip() and kk.strip(), f"{area}.{name}"
        ru_fields = sorted((f, s, c or "") for _, f, s, c in formatter.parse(ru) if f is not None)
        kk_fields = sorted((f, s, c or "") for _, f, s, c in formatter.parse(kk) if f is not None)
        assert ru_fields == kk_fields, f"{area}.{name}"


async def test_registration_acknowledgement_uses_explicit_recipient_locale(db_session, monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(auth_service.email_service, "send_verification_email", send)
    # The service's explicit locale also applies outside an HTTP request.
    with use_locale("ru"):
        response = await auth_service.register(
            f"{uuid.uuid4()}@example.com", "Testpass123!", db_session, locale="kk",
        )
    assert response.message == "Код электрондық поштаға жіберілді"
    assert send.await_args.kwargs == {"locale": "kk"}


@pytest.mark.parametrize("locale", ["ru", "kk"])
@pytest.mark.parametrize("account_exists", [False, True])
async def test_reset_acknowledgement_uses_request_locale_without_exposing_account(
    monkeypatch, locale, account_exists,
):
    monkeypatch.setattr(auth, "_check_rate_limit", AsyncMock())
    initiate = AsyncMock(side_effect=None if account_exists else ValueError("Account not found"))
    monkeypatch.setattr(auth.password_reset_service, "initiate_reset", initiate)
    expected = {
        "ru": "If an account exists, a reset code has been sent.",
        "kk": "Егер тіркелгі бар болса, құпиясөзді қалпына келтіру коды жіберілді.",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/auth/forgot-password",
            headers={"Accept-Language": locale},
            json={"email": "student@example.com"},
        )
    assert response.status_code == 200
    assert response.json() == {"message": expected[locale]}
    assert initiate.await_count == 1


@pytest.mark.parametrize("locale", ["ru", "kk"])
def test_nested_http_error_keeps_contract_and_interpolated_values(locale, monkeypatch):
    # Even a future KK translation must not change the stable legacy detail.
    monkeypatch.setitem(api_errors.KK, "allocation_total_mismatch", "translated {total} {actual_total}")
    with use_locale(locale), pytest.raises(HTTPException) as error:
        ipsative_battery.validate_allocation({"a": 4, "b": 5}, expected_items=["a", "b"], total=10)
    assert error.value.status_code == 422
    assert error.value.detail == {
        "detail": "Allocation must sum to exactly 10 points, got 9",
        "expected_total": 10,
        "actual_total": 9,
    }


def test_validation_resolves_locale_at_call_time_without_changing_password_rules(monkeypatch):
    monkeypatch.setitem(api_errors.KK, "password_letter_required", "Құпиясөзде әріп болуы керек")
    with use_locale("kk"), pytest.raises(ValidationError) as error:
        RegisterRequest(email="student@example.com", password="12345678")
    assert "Құпиясөзде әріп болуы керек" in str(error.value)
    with use_locale("ru"), pytest.raises(ValidationError) as error:
        RegisterRequest(email="student@example.com", password="12345678")
    assert "Password must contain at least one letter" in str(error.value)
    with use_locale("kk"):
        request = RegisterRequest(email="student@example.com", password="Testpass123!")
    assert request.password == "Testpass123!"


def test_dynamic_validation_values_keep_their_original_format():
    with pytest.raises(ValidationError) as error:
        UpdateMeRequest(locale="en")
    assert "locale must be one of ['kk', 'ru']" in str(error.value)
    with pytest.raises(ValidationError) as error:
        CertificateItem(type="ielts", score=10)
    assert "score for ielts must be between 0.0 and 9.0" in str(error.value)
    with pytest.raises(HTTPException) as error:
        _subtest_or_404(parse_bank(load_v1_document()), 99)
    assert error.value.detail == "No such АСТУР subtest: 99"
