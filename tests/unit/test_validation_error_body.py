"""A 422 never repeats what the client sent.

FastAPI puts the rejected value into every validation error as `input`. For
the auth endpoints that value is a password, an emailed code or an invitation
token — and a 422 body is what browser consoles and error trackers keep.
"""

import httpx
import pytest

from app.main import app

SECRET = "hunter2"


async def _post(path: str, body: dict) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(path, json=body)


@pytest.mark.parametrize(
    ("path", "body"),
    [
        # Too short a password — the built-in `string_too_short`.
        ("/api/v1/auth/register", {"email": "a@example.com", "password": SECRET}),
        # A value of the wrong type — the built-in `string_type`.
        ("/api/v1/auth/login", {"email": "a@example.com", "password": [SECRET]}),
        # A custom rule (`PydanticCustomError`) of the invitation form.
        ("/api/v1/auth/invitations/accept", {"token": "t" * 43, "password": SECRET}),
        # The value is rejected for its length — a localized message.
        ("/api/v1/auth/verify-email", {"email": "a@example.com", "code": SECRET * 10}),
    ],
    ids=["register", "login", "accept_invitation", "verify_email"],
)
async def test_rejected_value_is_not_echoed(path: str, body: dict) -> None:
    response = await _post(path, body)

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert errors, "the error list itself must survive"
    assert all("input" not in error for error in errors)
    assert SECRET not in response.text
    # What a form needs is still there.
    assert all({"type", "loc", "msg"} <= error.keys() for error in errors)
