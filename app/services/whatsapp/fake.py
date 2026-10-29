"""A stand-in WhatsApp provider for tests (ТЗ И-05): sends nowhere, keeps
what was sent, and builds events without any provider's format."""

import itertools
from datetime import datetime, timezone

from app.services.whatsapp.provider import Event, Message


class FakeWhatsApp:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self._ids = itertools.count(1)

    async def send_text(self, phone: str, text: str) -> str:
        self.sent.append((phone, text))
        return f"fake-out-{next(self._ids)}"

    def parse(self, payload: dict) -> list[Event]:
        return payload["events"]

    def incoming(self, phone: str, text: str, *, name: str | None = None, ad_id: str | None = None) -> Message:
        return Message(
            provider_id=f"fake-in-{next(self._ids)}", phone=phone, text=text, at=datetime.now(timezone.utc),
            sender_name=name, ad={"sourceType": "ad", "sourceId": ad_id} if ad_id else None,
        )
