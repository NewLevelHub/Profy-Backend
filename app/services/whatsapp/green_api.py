"""Green API (green-api.com) — the WhatsApp provider at the start (owner's
decision of 20.10). The token is part of every URL: neither is logged.

Webhook types used: incomingMessageReceived, outgoingMessageReceived (sent
from the phone), outgoingAPIMessageReceived (sent by the CRM),
outgoingMessageStatus. Group chats are ignored.
"""

import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.models.crm import MessageStatus
from app.services.whatsapp.provider import Event, Message, SendError, StatusUpdate

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

TIMEOUT = httpx.Timeout(20.0)
STATUSES = {
    "sent": MessageStatus.sent,
    "delivered": MessageStatus.delivered,
    "read": MessageStatus.read,
    "failed": MessageStatus.failed,
    "noAccount": MessageStatus.failed,
    "notInGroup": MessageStatus.failed,
}
# Media types → the mark shown instead of a text.
MEDIA = {
    "imageMessage": "[фото]",
    "videoMessage": "[видео]",
    "documentMessage": "[документ]",
    "audioMessage": "[голосовое]",
    "stickerMessage": "[стикер]",
    "locationMessage": "[геопозиция]",
    "contactMessage": "[контакт]",
}


def _url(method: str, *tail: str) -> str:
    base = settings.GREEN_API_URL.rstrip("/")
    path = "/".join((method, settings.GREEN_API_TOKEN_INSTANCE, *tail))
    return f"{base}/waInstance{settings.GREEN_API_ID_INSTANCE}/{path}"


def phone_of(chat_id: str) -> str | None:
    """`77051234567@c.us` → `+77051234567`; None for a group or other chat."""
    if not chat_id.endswith("@c.us"):
        return None
    digits = chat_id.split("@", 1)[0]
    return f"+{digits}" if digits.isdigit() else None


def chat_of(phone: str) -> str:
    return f"{phone.lstrip('+')}@c.us"


def _text(data: dict) -> tuple[str, str, dict | None]:
    """(text, kind, ad data) of `messageData`."""
    kind = data.get("typeMessage") or "text"
    if kind == "textMessage":
        return (data.get("textMessageData") or {}).get("textMessage") or "", "text", None
    if kind in ("extendedTextMessage", "quotedMessage"):
        ext = data.get("extendedTextMessageData") or {}
        ad = {
            k: ext[k]
            for k in ("sourceType", "sourceId", "sourceUrl", "ctwaClid", "sourceApp", "greetingMessageBody", "title")
            if ext.get(k)
        } or None
        return ext.get("text") or "", "text", ad
    caption = (data.get("fileMessageData") or {}).get("caption") or ""
    mark = MEDIA.get(kind, f"[{kind}]")
    return f"{mark} {caption}".strip(), kind.removesuffix("Message"), None


class GreenApi:
    async def send_text(self, phone: str, text: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(_url("sendMessage"), json={"chatId": chat_of(phone), "message": text})
        except httpx.HTTPError as error:
            raise SendError(type(error).__name__) from None
        body = response.json() if response.content else {}
        if response.status_code != 200 or not body.get("idMessage"):
            raise SendError(f"HTTP {response.status_code}")
        return body["idMessage"]

    def parse(self, payload: dict) -> list[Event]:
        kind = payload.get("typeWebhook")
        if kind == "outgoingMessageStatus":
            status = STATUSES.get(payload.get("status") or "")
            return [StatusUpdate(payload["idMessage"], status)] if status and payload.get("idMessage") else []
        if kind not in ("incomingMessageReceived", "outgoingMessageReceived", "outgoingAPIMessageReceived"):
            return []
        sender = payload.get("senderData") or {}
        phone = phone_of(sender.get("chatId") or "")
        if phone is None or not payload.get("idMessage"):
            return []
        text, message_kind, ad = _text(payload.get("messageData") or {})
        moment = datetime.fromtimestamp(int(payload.get("timestamp") or 0), tz=timezone.utc)
        return [Message(
            provider_id=payload["idMessage"], phone=phone, text=text, at=moment,
            outgoing=kind != "incomingMessageReceived", kind=message_kind,
            sender_name=(sender.get("senderName") or sender.get("chatName")) if kind == "incomingMessageReceived" else None,
            ad=ad, via_api=kind == "outgoingAPIMessageReceived",
        )]

    # ── local runs (scripts/whatsapp_poll.py) and setup ─────────────────────

    async def receive(self, timeout: int = 20) -> tuple[int, dict] | None:
        """The next queued notification (receiptId, body), or None."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout + 10.0)) as client:
            response = await client.get(_url("receiveNotification"), params={"receiveTimeout": timeout})
        body = response.json() if response.content else None
        return (body["receiptId"], body["body"]) if body else None

    async def delete(self, receipt_id: int) -> None:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            await client.delete(_url("deleteNotification", str(receipt_id)))

    async def set_settings(self, **values) -> dict:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(_url("setSettings"), json=values)
        return response.json()

    async def state(self) -> str | None:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(_url("getStateInstance"))
        return (response.json() if response.content else {}).get("stateInstance")
