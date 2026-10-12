"""Swagger UI and the OpenAPI schema can be switched off (SEC-11): together
they are the full map of the API, admin routes included, and production does
not hand it to anonymous visitors."""

import httpx
import pytest
from fastapi import FastAPI

from app import main
from app.config import Settings


async def _statuses(app: FastAPI) -> dict[str, int]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return {path: (await client.get(path)).status_code for path in ("/docs", "/openapi.json", "/redoc")}


def _app_with_docs(monkeypatch: pytest.MonkeyPatch, *, enabled: bool) -> FastAPI:
    monkeypatch.setattr(main.settings, "API_DOCS_ENABLED", enabled)
    app = FastAPI(**main.docs_routes())

    @app.get("/api/v1/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    return app


async def test_docs_are_served_where_the_stack_allows_them(monkeypatch: pytest.MonkeyPatch) -> None:
    statuses = await _statuses(_app_with_docs(monkeypatch, enabled=True))

    assert statuses == {"/docs": 200, "/openapi.json": 200, "/redoc": 404}


async def test_nothing_describes_the_api_when_docs_are_off(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app_with_docs(monkeypatch, enabled=False)

    assert await _statuses(app) == {"/docs": 404, "/openapi.json": 404, "/redoc": 404}
    # The API itself is untouched.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/ping")).status_code == 200


def test_the_switch_is_an_ordinary_boolean_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    # On unless a stack says otherwise; docker-compose.prod.yml pins it off
    # (tests/deployment/test_isolation.py).
    assert Settings.model_fields["API_DOCS_ENABLED"].default is True
    monkeypatch.setenv("API_DOCS_ENABLED", "false")
    assert Settings().API_DOCS_ENABLED is False
