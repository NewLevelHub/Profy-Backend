"""Resend webhook → delivery status of staff invitation emails."""

import base64
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invitation import Invitation, InvitationEmailStatus
from app.models.user import UserRole
from app.routers import webhooks
from app.routers.webhooks import svix_signature
from app.services.invitation_service import hash_token

URL = "/api/v1/webhooks/resend"
SECRET = "whsec_" + base64.b64encode(b"resend-webhook-test-secret-32by").decode()


@pytest.fixture(autouse=True)
def _webhook_secret(monkeypatch) -> None:
    monkeypatch.setattr(webhooks.settings, "RESEND_WEBHOOK_SECRET", SECRET)


async def _add_invitation(
    db: AsyncSession, *, status: InvitationEmailStatus = InvitationEmailStatus.sent
) -> Invitation:
    now = datetime.now(timezone.utc)
    invitation = Invitation(
        email=f"{uuid.uuid4()}@example.com",
        role=UserRole.psychologist,
        locale="ru",
        token_hash=hash_token(uuid.uuid4().hex),
        expires_at=now + timedelta(hours=72),
        email_message_id=f"msg-{uuid.uuid4()}",
        email_status=status,
        email_status_at=now,
    )
    db.add(invitation)
    await db.flush()
    return invitation


def _signed(event: dict, *, secret: str = SECRET, timestamp: int | None = None) -> tuple[bytes, dict]:
    body = json.dumps(event).encode()
    msg_id = f"msg_{uuid.uuid4().hex}"
    ts = str(timestamp if timestamp is not None else int(time.time()))
    headers = {
        "svix-id": msg_id,
        "svix-timestamp": ts,
        "svix-signature": f"v1,{svix_signature(secret, msg_id, ts, body)}",
        "content-type": "application/json",
    }
    return body, headers


def _event(kind: str, message_id: str) -> dict:
    return {
        "type": kind,
        "created_at": "2026-10-07T10:00:00.000Z",
        "data": {"email_id": message_id, "to": ["someone@example.com"]},
    }


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("email.delivered", InvitationEmailStatus.delivered),
        ("email.delivery_delayed", InvitationEmailStatus.delayed),
        ("email.bounced", InvitationEmailStatus.bounced),
        ("email.complained", InvitationEmailStatus.complained),
        ("email.failed", InvitationEmailStatus.failed),
        ("email.suppressed", InvitationEmailStatus.suppressed),
    ],
)
async def test_event_updates_the_invitation(
    client: httpx.AsyncClient, db_session: AsyncSession, kind: str, expected: InvitationEmailStatus
) -> None:
    invitation = await _add_invitation(db_session)
    body, headers = _signed(_event(kind, invitation.email_message_id))

    response = await client.post(URL, content=body, headers=headers)

    assert response.status_code == 204
    await db_session.refresh(invitation)
    assert invitation.email_status == expected
    assert invitation.email_status_at == datetime(2026, 10, 7, 10, tzinfo=timezone.utc)


async def test_status_never_moves_back(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    """A late "delayed" after "delivered" (or anything after a bounce) is ignored."""
    invitation = await _add_invitation(db_session, status=InvitationEmailStatus.bounced)
    body, headers = _signed(_event("email.delivered", invitation.email_message_id))

    response = await client.post(URL, content=body, headers=headers)

    assert response.status_code == 204
    await db_session.refresh(invitation)
    assert invitation.email_status == InvitationEmailStatus.bounced


@pytest.mark.parametrize(
    "event",
    [
        _event("email.bounced", "msg-of-a-verification-email"),
        _event("email.opened", "msg-anything"),
        {"type": "email.bounced"},
    ],
    ids=["unknown_email", "untracked_type", "no_data"],
)
async def test_other_events_are_acknowledged(
    client: httpx.AsyncClient, db_session: AsyncSession, event: dict
) -> None:
    invitation = await _add_invitation(db_session)
    body, headers = _signed(event)

    response = await client.post(URL, content=body, headers=headers)

    assert response.status_code == 204
    await db_session.refresh(invitation)
    assert invitation.email_status == InvitationEmailStatus.sent


@pytest.mark.parametrize("tamper", ["secret", "body", "stale", "missing"])
async def test_unsigned_or_tampered_request_is_401(
    client: httpx.AsyncClient, db_session: AsyncSession, tamper: str
) -> None:
    invitation = await _add_invitation(db_session)
    event = _event("email.bounced", invitation.email_message_id)
    other_secret = "whsec_" + base64.b64encode(b"some-other-secret-of-32-bytes!!").decode()
    body, headers = _signed(
        event,
        secret=other_secret if tamper == "secret" else SECRET,
        timestamp=int(time.time()) - 600 if tamper == "stale" else None,
    )
    if tamper == "body":
        body = body.replace(b"bounced", b"delivered")
    if tamper == "missing":
        headers.pop("svix-signature")

    response = await client.post(URL, content=body, headers=headers)

    assert response.status_code == 401
    await db_session.refresh(invitation)
    assert invitation.email_status == InvitationEmailStatus.sent


async def test_endpoint_is_off_without_secret(client: httpx.AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(webhooks.settings, "RESEND_WEBHOOK_SECRET", "")
    body, headers = _signed(_event("email.bounced", "msg-x"))

    response = await client.post(URL, content=body, headers=headers)

    assert response.status_code == 404
