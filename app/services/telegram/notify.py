"""Sending one message to a linked specialist, shared by the reminders."""

from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telegram import TelegramLink
from app.services.telegram import client


def button(label: str, url: str) -> tuple[str, str]:
    """A «Перейти …» button to `url` in Profile. Telegram refuses a button to
    `localhost` («Wrong HTTP URL») but takes 127.0.0.1, so a local address
    goes there instead — the same dev server (it has to listen on 127.0.0.1)."""
    parts = urlsplit(url)
    if parts.hostname == "localhost":
        netloc = "127.0.0.1" + (f":{parts.port}" if parts.port else "")
        url = urlunsplit(parts._replace(netloc=netloc))
    return label, url


async def send(db: AsyncSession | None, chat_id: int, text: str, link: tuple[str, str] | None = None) -> bool:
    """True when Telegram took it. A chat that blocked the bot is unlinked
    (committed), so nothing more is written there — unless `db` is None: a
    send from inside someone else's request must not commit their session;
    the next reminder check unlinks it then."""
    try:
        return await client.send_message(chat_id, text, link)
    except client.ChatGone:
        if db is not None:
            await db.execute(delete(TelegramLink).where(TelegramLink.chat_id == chat_id))
            await db.commit()
        return False
