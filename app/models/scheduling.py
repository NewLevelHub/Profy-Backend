"""Specialist schedule (ТЗ CRM Profile v4.1 §4.6, §5.1; PRO-512).

The single store of specialists' availability, read and written by both the
specialist cabinet and the CRM (contract: docs/frontend-scheduling-api-contract.md).
Times are UTC; the business calendar is Asia/Almaty (`app.services.tz`).

A slot is a 30-minute cell. Only non-`closed` cells have a row: a missing
row means the specialist does not work then, so a day off is simply no rows.
A booked slot keeps its row, in state `booked`, pointing at the meeting.
"""

import enum
import uuid
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    SmallInteger,
    Time,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SlotState(str, enum.Enum):
    free = "free"
    # «Занято (личное)»: the specialist's own client, no details (ТЗ §4.6 п.6).
    personal = "personal"
    # Taken by a meeting (`meeting_id`); only a booking sets it.
    booked = "booked"


class SpecialistSlot(Base):
    __tablename__ = "specialist_slots"

    specialist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # Slot start, UTC, on a :00/:30 boundary. With `specialist_id` the primary
    # key, so a specialist can never hold two rows for one slot.
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, index=True)
    state: Mapped[SlotState] = mapped_column(
        Enum(SlotState, native_enum=False, length=16), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True, index=True
    )


class MeetingType(str, enum.Enum):
    intro30 = "intro30"  # Вступительный созвон
    main60 = "main60"    # Основной созвон / созвон по «Консультации»


class MeetingStatus(str, enum.Enum):
    pending = "pending"      # Ожидание
    confirmed = "confirmed"  # Подтвердил
    done = "done"            # Проведена
    no_show = "no_show"      # Не пришёл
    cancelled = "cancelled"


class Meeting(Base):
    """A call booked in the shared schedule (ТЗ §3.2 «Встреча», §3.9).

    `handoff` is the handoff card the manager filled (ТЗ §3.10): it is what
    the specialist sees about the client, without prices or the sales chat."""

    __tablename__ = "meetings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crm_deals.id", ondelete="SET NULL"), nullable=True, index=True
    )
    specialist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[MeetingType] = mapped_column(Enum(MeetingType, native_enum=False, length=16), nullable=False)
    status: Mapped[MeetingStatus] = mapped_column(
        Enum(MeetingStatus, native_enum=False, length=16), nullable=False, server_default="pending"
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    handoff: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SpecialistWeekPublication(Base):
    """«Неделя выставлена»: drives the Friday reminder and the owner's
    "week not set" mark. Publishing does not hide or reveal slots."""

    __tablename__ = "specialist_week_publications"

    specialist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # Monday, Almaty date.
    week_start: Mapped[date] = mapped_column(Date, primary_key=True)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class SpecialistWeekTemplate(Base):
    """A specialist's repeating week: `{"1": [{"start": "10:00", "end": "13:00",
    "state": "free"}], …, "7": […]}` — Almaty wall time, Monday = "1"."""

    __tablename__ = "specialist_week_templates"

    specialist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    days: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SchedulingSettings(Base):
    """Owner's scheduling settings — a single row, `id = 1`."""

    __tablename__ = "scheduling_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    # 1 = Monday … 7 = Sunday; the reminder about next week (ТЗ §4.6 п.2).
    week_reminder_weekday: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("5")
    )
    week_reminder_time: Mapped[time] = mapped_column(
        Time, nullable=False, server_default=text("'18:00'")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class SpecialistWeekReminder(Base):
    """«Выставьте расписание» was sent for this week (PRO-560): at most one
    reminder per specialist per week, however often the check runs."""

    __tablename__ = "specialist_week_reminders"

    specialist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # Monday of the week the specialist was asked to set (the next week).
    week_start: Mapped[date] = mapped_column(Date, primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
