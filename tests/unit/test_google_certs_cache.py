"""Google's signing certificates are fetched once, not on every login (SEC-15).

`verify_oauth2_token` asks its transport for the certificates before it looks
at the token, so without a cache every call to `/auth/google` — a garbage
token included — is an outbound HTTPS request.
"""

from http import HTTPStatus
from types import SimpleNamespace

import pytest

from app.services import oauth_service

CERTS_URL = "https://www.googleapis.com/oauth2/v1/certs"


class _FakeGoogleRequest:
    """Stands in for `google.auth.transport.requests.Request`."""

    calls: list[tuple[str, str, dict]] = []
    status = HTTPStatus.OK

    def __call__(self, url, method="GET", **kwargs):
        type(self).calls.append((url, method, kwargs))
        return SimpleNamespace(status=type(self).status, data=b"{}")


@pytest.fixture(autouse=True)
def fake_transport(monkeypatch):
    _FakeGoogleRequest.calls = []
    _FakeGoogleRequest.status = HTTPStatus.OK
    monkeypatch.setattr(oauth_service.google_requests, "Request", _FakeGoogleRequest)
    monkeypatch.setattr(oauth_service, "_certs_cache", {})
    return _FakeGoogleRequest


def test_certificates_are_fetched_once(fake_transport) -> None:
    request = oauth_service._CachingRequest()

    first = request(CERTS_URL, method="GET")
    second = request(CERTS_URL, method="GET")

    assert len(fake_transport.calls) == 1
    assert second is first


def test_cache_is_shared_between_worker_transports(fake_transport) -> None:
    """Each worker thread has its own transport; the certificates one of
    them fetched serve the others."""
    oauth_service._CachingRequest()(CERTS_URL)
    oauth_service._CachingRequest()(CERTS_URL)

    assert len(fake_transport.calls) == 1


def test_certificates_are_fetched_again_after_the_ttl(fake_transport, monkeypatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(oauth_service.time, "monotonic", lambda: now[0])
    request = oauth_service._CachingRequest()

    request(CERTS_URL)
    now[0] += oauth_service._CERTS_TTL_SECONDS - 1
    request(CERTS_URL)
    assert len(fake_transport.calls) == 1

    now[0] += 2
    request(CERTS_URL)
    assert len(fake_transport.calls) == 2


def test_a_failed_fetch_is_not_remembered(fake_transport) -> None:
    request = oauth_service._CachingRequest()
    fake_transport.status = HTTPStatus.SERVICE_UNAVAILABLE

    assert request(CERTS_URL).status == HTTPStatus.SERVICE_UNAVAILABLE
    fake_transport.status = HTTPStatus.OK
    assert request(CERTS_URL).status == HTTPStatus.OK

    assert len(fake_transport.calls) == 2


def test_the_fetch_has_a_short_timeout(fake_transport) -> None:
    oauth_service._CachingRequest()(CERTS_URL)

    (_, _, kwargs), = fake_transport.calls
    assert kwargs["timeout"] == oauth_service._CERTS_FETCH_TIMEOUT_SECONDS


def test_other_methods_bypass_the_cache(fake_transport) -> None:
    request = oauth_service._CachingRequest()

    request(CERTS_URL, method="POST")
    request(CERTS_URL, method="POST")

    assert [method for _, method, _ in fake_transport.calls] == ["POST", "POST"]
