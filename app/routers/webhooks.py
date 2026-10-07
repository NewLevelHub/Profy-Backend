"""Inbound webhooks from third-party services.

Resend → delivery of staff invitation emails. Resend signs webhooks with
Svix: HMAC-SHA256 over "{svix-id}.{svix-timestamp}.{raw body}", keyed with
the base64 part of the "whsec_…" secret. Setup: .env.example
(`RESEND_WEBHOOK_SECRET`).
"""

import base64
import binascii
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.invitation import InvitationEmailStatus
from app.services import invitation_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])

# Svix rejects older deliveries the same way — limits replay of a captured request.
_SIGNATURE_TOLERANCE_SECONDS = 5 * 60

_RESEND_EVENTS: dict[str, InvitationEmailStatus] = {
    "email.delivered": InvitationEmailStatus.delivered,
    "email.delivery_delayed": InvitationEmailStatus.delayed,
    "email.bounced": InvitationEmailStatus.bounced,
    "email.complained": InvitationEmailStatus.complained,
    "email.failed": InvitationEmailStatus.failed,
    "email.suppressed": InvitationEmailStatus.suppressed,
}


def svix_signature(secret: str, msg_id: str, timestamp: str, body: bytes) -> str:
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = f"{msg_id}.{timestamp}.".encode() + body
    return base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()


def _signature_valid(request: Request, body: bytes) -> bool:
    msg_id = request.headers.get("svix-id", "")
    timestamp = request.headers.get("svix-timestamp", "")
    header = request.headers.get("svix-signature", "")
    try:
        if abs(time.time() - int(timestamp)) > _SIGNATURE_TOLERANCE_SECONDS:
            return False
        expected = svix_signature(settings.RESEND_WEBHOOK_SECRET, msg_id, timestamp, body)
    except (ValueError, binascii.Error):
        return False
    # "v1,<sig> v1,<sig>" — several while the secret is being rotated.
    return any(
        version == "v1" and hmac.compare_digest(signature, expected)
        for version, _, signature in (part.partition(",") for part in header.split())
    )


def _event_time(raw: object) -> datetime:
    try:
        at = datetime.fromisoformat(str(raw))
    except ValueError:
        return datetime.now(timezone.utc)
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


@router.post("/resend", status_code=status.HTTP_204_NO_CONTENT)
async def resend_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    if not settings.RESEND_WEBHOOK_SECRET:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    body = await request.body()
    if not _signature_valid(request, body):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        event = json.loads(body)
        email_status = _RESEND_EVENTS.get(event["type"])
        message_id = event["data"]["email_id"]
    except (ValueError, KeyError, TypeError):
        logger.warning("Resend webhook: unexpected payload shape")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # Other event types and non-invitation emails are acknowledged and
    # dropped — a non-2xx answer would only make Resend retry them.
    if email_status is not None and isinstance(message_id, str):
        await invitation_service.record_email_event(
            db, message_id, email_status, _event_time(event.get("created_at"))
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
