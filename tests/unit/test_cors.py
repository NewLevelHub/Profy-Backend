"""CORS policy (SEC-03): only configured origins may read API responses
cross-origin, and never in credentials mode.

Every request here is answered without touching the database: a preflight
is handled by the middleware itself, and `/openapi.json` is static.
"""
import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings, settings
from app.main import app

FOREIGN_ORIGIN = "https://evil.example"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _preflight_headers(origin: str, method: str = "POST", headers: str = "authorization,content-type") -> dict:
    return {
        "Origin": origin,
        "Access-Control-Request-Method": method,
        "Access-Control-Request-Headers": headers,
    }


@pytest.fixture
def allowed_origin() -> str:
    if not settings.CORS_ALLOWED_ORIGINS:
        pytest.skip("CORS_ALLOWED_ORIGINS is empty in this environment")
    return settings.CORS_ALLOWED_ORIGINS[0]


async def test_foreign_origin_is_not_reflected_on_a_simple_request():
    async with _client() as client:
        response = await client.get("/openapi.json", headers={"Origin": FOREIGN_ORIGIN})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers


async def test_foreign_origin_is_not_reflected_when_a_cookie_is_sent():
    async with _client() as client:
        response = await client.get(
            "/openapi.json", headers={"Origin": FOREIGN_ORIGIN, "Cookie": "session=1"},
        )
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers


async def test_foreign_origin_preflight_is_rejected():
    async with _client() as client:
        response = await client.options(
            "/api/v1/auth/login", headers=_preflight_headers(FOREIGN_ORIGIN),
        )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers


async def test_allowed_origin_can_read_responses_without_credentials_mode(allowed_origin):
    async with _client() as client:
        response = await client.get("/openapi.json", headers={"Origin": allowed_origin})
    assert response.headers["access-control-allow-origin"] == allowed_origin
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
async def test_allowed_origin_preflight_accepts_the_headers_the_spa_sends(allowed_origin, method):
    async with _client() as client:
        response = await client.options(
            "/api/v1/auth/login",
            headers=_preflight_headers(
                allowed_origin, method, "authorization,content-type,accept-language",
            ),
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == allowed_origin
    assert "access-control-allow-credentials" not in response.headers


async def test_allowed_origin_preflight_rejects_an_unlisted_header(allowed_origin):
    async with _client() as client:
        response = await client.options(
            "/api/v1/auth/login",
            headers=_preflight_headers(allowed_origin, headers="content-type,x-anything"),
        )
    assert response.status_code == 400


async def test_allowed_origin_preflight_rejects_an_unlisted_method(allowed_origin):
    async with _client() as client:
        response = await client.options(
            "/api/v1/auth/login", headers=_preflight_headers(allowed_origin, method="TRACE"),
        )
    assert response.status_code == 400


def test_origins_are_read_from_a_comma_separated_env_value(monkeypatch):
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS", "https://profile.newlevelhub.kz, http://localhost:5173/ ,",
    )
    assert Settings().CORS_ALLOWED_ORIGINS == [
        "https://profile.newlevelhub.kz",
        "http://localhost:5173",
    ]


def test_an_empty_env_value_allows_no_origin(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "")
    assert Settings().CORS_ALLOWED_ORIGINS == []


@pytest.mark.parametrize(
    "value",
    [
        "*",
        "https://*.newlevelhub.kz",
        "profile.newlevelhub.kz",
        "https://profile.newlevelhub.kz/app",
        "https://profile.newlevelhub.kz?x=1",
        "ftp://profile.newlevelhub.kz",
        "null",
    ],
)
def test_a_value_that_is_not_an_exact_origin_fails_at_startup(monkeypatch, value):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", value)
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        Settings()
