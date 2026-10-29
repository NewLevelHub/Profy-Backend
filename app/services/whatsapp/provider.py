"""What the CRM needs from a WhatsApp provider, provider-free."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.models.crm import MessageStatus


@dataclass(frozen=True)
class Message:
    """A message in a one-to-one chat. `outgoing` — sent from the sales
    number (from the phone, or by the CRM through the provider)."""

    provider_id: str
    phone: str  # +7XXXXXXXXXX (or the international digits)
    text: str
    at: datetime
    outgoing: bool = False
    kind: str = "text"
    sender_name: str | None = None
    # Ad data of a message that came from a click-to-WhatsApp ad: sourceId
    # (the ad's id), sourceUrl, ctwaClid, greetingMessageBody… (ТЗ §3.12.1).
    ad: dict[str, Any] | None = None
    # Sent by the CRM itself (already stored when sent).
    via_api: bool = False

    @property
    def ad_id(self) -> str | None:
        return (self.ad or {}).get("sourceId") if (self.ad or {}).get("sourceType") == "ad" else None


@dataclass(frozen=True)
class StatusUpdate:
    provider_id: str
    status: MessageStatus


Event = Message | StatusUpdate


class SendError(Exception):
    """The provider did not take the message; nothing in it is secret."""


class WhatsAppProvider(Protocol):
    async def send_text(self, phone: str, text: str) -> str:
        """Send; the provider's message id. Raises `SendError`."""

    def parse(self, payload: dict) -> list[Event]:
        """A webhook (or polled notification) body → events; [] to ignore."""


@dataclass
class _Holder:
    instance: WhatsAppProvider | None = field(default=None)


_holder = _Holder()


def get() -> WhatsAppProvider:
    """The configured provider. Tests put a stub here with `use`."""
    if _holder.instance is None:
        from app.services.whatsapp.green_api import GreenApi

        _holder.instance = GreenApi()
    return _holder.instance


def use(instance: WhatsAppProvider | None) -> None:
    _holder.instance = instance
