"""CRM of the sales team (ТЗ CRM Profile v4.1, part 1, §3.2–3.3).

Leads are entered by hand for now (no WhatsApp, no ads data). Stages 1–6 move
by hand; 7 «Диагностика пройдена» and 8 «Отчёт опубликован» also follow the
linked student account (app/services/crm/progress.py). Contract: docs/frontend-crm-api-contract.md.
"""

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DealStage(str, enum.Enum):
    """The funnel, in order (ТЗ §3.3). Index = position on the board.

    ТЗ's «Разбор назначен» is not a stage: the specialist sets the second
    call from the first call on, before or after the test, so it cannot sit
    in one line with «Диагностика пройдена». The deal card shows it instead
    (`DealCard.review_start`)."""

    unsorted = "unsorted"                    # 1 Неразобранное
    qualification = "qualification"          # 2 Квалификация
    consultation = "consultation"            # 3 Консультация (звонок менеджера)
    closing = "closing"                      # 4 Дожим
    invoice = "invoice"                      # 5 Счёт выставлен
    paid = "paid"                            # 6 Оплачено — only by marking the payment
    diagnostics_done = "diagnostics_done"    # 7 Диагностика пройдена
    report_published = "report_published"    # 8 Отчёт опубликован
    review_done = "review_done"              # 9 Разбор проведён


STAGE_ORDER = list(DealStage)


class DealResult(str, enum.Enum):
    open = "open"
    won = "won"      # Успешно реализовано
    lost = "lost"    # Закрыто и не реализовано


class LostReason(str, enum.Enum):
    non_target = "non_target"
    refused = "refused"
    no_answer = "no_answer"
    duplicate = "duplicate"
    cancelled = "cancelled"
    no_show = "no_show"
    refund = "refund"
    other = "other"


class PaymentMethod(str, enum.Enum):
    cash = "cash"
    transfer = "transfer"


class CrmParent(Base):
    """The buyer. Duplicates are found by the normalized phone (`+7XXXXXXXXXX`)."""

    __tablename__ = "crm_parents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Consent to process the child's personal data (ТЗ §3.8): None = not asked.
    consent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CrmStudent(Base):
    __tablename__ = "crm_students"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crm_parents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    age: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    grade: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    study_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    russian_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CrmTariff(Base):
    """Price list, kept by the owner in the CRM. The price is copied into a
    deal when the tariff is picked and never recalculated after (ТЗ §3.7)."""

    __tablename__ = "crm_tariffs"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    # A specialist's call and their review (and edits) of the report before
    # the student sees it. Without it there is no call and the report is
    # published as soon as it is built.
    # Copied into the deal with the price (CrmDeal.psychologist_review).
    psychologist_review: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # «Что входит» — shown in the price list; the owner edits it in the CRM.
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # An archived tariff is not offered for new deals; deals that have it keep it.
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    sort: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")


class CrmDeal(Base):
    """One tariff sold to one student (ТЗ §1.4)."""

    __tablename__ = "crm_deals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crm_parents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crm_students.id", ondelete="SET NULL"), nullable=True
    )
    stage: Mapped[DealStage] = mapped_column(
        Enum(DealStage, native_enum=False, length=32), nullable=False, index=True
    )
    result: Mapped[DealResult] = mapped_column(
        Enum(DealResult, native_enum=False, length=16), nullable=False, server_default="open", index=True
    )
    lost_reason: Mapped[LostReason | None] = mapped_column(Enum(LostReason, native_enum=False, length=32))
    close_comment: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # NULL = nobody took it yet («Неразобранное»).
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The student's Profile account, linked by the invite link (ТЗ §4.4) or
    # by the owner. Test and report progress of this account moves stages 7–8.
    student_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Set by the booking (the system picks the specialist).
    specialist_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Qualification (ТЗ §3.6): None = not decided yet.
    is_target: Mapped[bool | None] = mapped_column(Boolean)
    non_target_reason: Mapped[str | None] = mapped_column(Text)
    tariff_code: Mapped[str | None] = mapped_column(ForeignKey("crm_tariffs.code"))
    price: Mapped[int | None] = mapped_column(Integer)
    # The tariff's psychologist_review on the day it was chosen, like the
    # price: decides whether the student's report waits for a psychologist
    # (app/services/crm/progress.report_needs_review). None — no tariff.
    psychologist_review: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    discount: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    paid_amount: Mapped[int | None] = mapped_column(Integer)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_method: Mapped[PaymentMethod | None] = mapped_column(Enum(PaymentMethod, native_enum=False, length=16))
    source: Mapped[str | None] = mapped_column(String(255))
    first_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @property
    def total(self) -> int | None:
        return None if self.price is None else max(self.price - self.discount, 0)


class CrmDealEvent(Base):
    """The deal's feed: stage moves, payment, notes, booking — who and when."""

    __tablename__ = "crm_deal_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crm_deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Set in Python, not `now()`: Postgres `now()` is the transaction start,
    # so two events of one request (stage + payment) would tie and the feed
    # order would be arbitrary.
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # created | accepted | stage | qualified | tariff | payment | payment_cancelled
    # | consent | closed | note | booked | manager | updated | invite
    # | student_linked | payment_check. Automatic ones have no actor.
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    text: Mapped[str | None] = mapped_column(Text)


class CrmStudentInvite(Base):
    """One-time link that registers (or signs in) the student and ties the
    account to the deal (ТЗ §4.4, П2-10/П2-11). A new link revokes the
    previous one. The token is kept hashed, plus encrypted so the manager can
    copy the link again."""

    __tablename__ = "crm_student_invites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crm_deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskType(str, enum.Enum):
    call = "call"
    message = "message"
    meeting = "meeting"
    payment_check = "payment_check"  # «Проверить оплату»
    reschedule = "reschedule"        # a manager asks the owner to move a call
    other = "other"


class CrmTask(Base):
    """A to-do with a deadline (ТЗ §3.11). A sales manager sets tasks only for
    themself; the owner and the head of sales set them for anyone in sales."""

    __tablename__ = "crm_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crm_deals.id", ondelete="CASCADE"), nullable=True, index=True
    )
    assignee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[TaskType] = mapped_column(Enum(TaskType, native_enum=False, length=32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
