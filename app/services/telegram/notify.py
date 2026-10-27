"""Sending one message to a linked specialist, shared by the reminders."""

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telegram import TelegramLink
from app.services.telegram import client


def with_link(text: str, url: str, label: str, line: str) -> tuple[str, tuple[str, str] | None]:
    """The message and its button. Telegram takes a button only with a
    public https link; elsewhere (locally) the link goes into the text as
    `line`, which has a `{url}` placeholder."""
    if url.startswith("https://"):
        return text, (label, url)
    return f"{text}\n{line.format(url=url)}", None


async def send(db: AsyncSession, chat_id: int, text: str, button: tuple[str, str] | None = None) -> bool:
    """True when Telegram took it. A chat that blocked the bot is unlinked
    (committed), so nothing more is written there."""
    try:
        return await client.send_message(chat_id, text, button)
    except client.ChatGone:
        await db.execute(delete(TelegramLink).where(TelegramLink.chat_id == chat_id))
        await db.commit()
        return False
