"""Telegram for specialists (ТЗ §4.6, B6): which chat a specialist linked and
which call reminders went out. Off until the bot token is set
(`settings.telegram_enabled`); the tables simply stay empty.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TelegramLink(Base):
    """The specialist's chat with the bot: one chat per account, one account per chat."""

    __tablename__ = "telegram_links"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TelegramLinkCode(Base):
    """A one-time code behind the «Подключить Telegram» link. The bot gets it
    in `/start <code>`; only its keyed hash is stored. A new link replaces
    the previous one."""

    __tablename__ = "telegram_link_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TelegramMeetingReminder(Base):
    """A call reminder that went out: at most one of each kind per call,
    however often the check runs. A moved call is a new meeting row, so it
    is reminded again."""

    __tablename__ = "telegram_meeting_reminders"

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True
    )
    # "day" — 24 hours before, "hour" — 1 hour before.
    kind: Mapped[str] = mapped_column(String(8), primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
