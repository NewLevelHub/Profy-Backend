"""CRM deals board and booking. Contract: docs/frontend-crm-api-contract.md."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.models.crm import DealResult, DealStage, LostReason, PaymentMethod

Name = Annotated[str, Field(min_length=1, max_length=255)]
ShortText = Annotated[str, Field(max_length=255)]
LongText = Annotated[str, Field(max_length=4000)]
Phone = Annotated[str, Field(max_length=32)]


class TariffItem(BaseModel):
    code: str
    name: str
    price: int
    meeting_minutes: int


class CrmMeta(BaseModel):
    stages: list[DealStage]
    tariffs: list[TariffItem]
    lost_reasons: list[LostReason]


class ParentIn(BaseModel):
    full_name: Name
    phone: Phone | None = None
    email: Annotated[str, Field(max_length=320)] | None = None
    city: Annotated[str, Field(max_length=120)] | None = None


class StudentIn(BaseModel):
    full_name: Annotated[str, Field(max_length=255)] | None = None
    age: Annotated[int, Field(ge=5, le=25)] | None = None
    gender: Literal["male", "female"] | None = None
    grade: Annotated[int, Field(ge=1, le=12)] | None = None
    city: Annotated[str, Field(max_length=120)] | None = None
    study_language: Literal["ru", "kk", "en", "other"] | None = None
    russian_level: Literal["fluent", "medium", "weak"] | None = None


class DealCreate(BaseModel):
    """A lead entered by hand. Pass `parent_id` to add a deal to a known
    client (found by phone) instead of creating a duplicate."""

    parent: ParentIn | None = None
    parent_id: uuid.UUID | None = None
    student: StudentIn | None = None
    source: ShortText | None = None
    first_message: LongText | None = None


class DealPatch(BaseModel):
    """Every field optional; only the ones sent change."""

    parent: ParentIn | None = None
    student: StudentIn | None = None
    is_target: bool | None = None
    non_target_reason: Annotated[str, Field(max_length=1000)] | None = None
    tariff_code: Annotated[str, Field(max_length=32)] | None = None
    discount: Annotated[int, Field(ge=0, le=10_000_000)] | None = None
    source: ShortText | None = None
    manager_id: uuid.UUID | None = None


class StageMove(BaseModel):
    stage: DealStage


class PaymentIn(BaseModel):
    amount: Annotated[int, Field(gt=0, le=10_000_000)]
    method: PaymentMethod
    paid_at: datetime | None = None


class ConsentIn(BaseModel):
    given: bool


class CloseIn(BaseModel):
    result: Literal["won", "lost"]
    reason: LostReason | None = None
    comment: Annotated[str, Field(max_length=1000)] | None = None


class NoteIn(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=4000)]


class Handoff(BaseModel):
    """Handoff card (ТЗ §3.10): all required except the manager's comment."""

    student_name: Name
    age: Annotated[int, Field(ge=5, le=25)]
    gender: Literal["male", "female"]
    grade: Annotated[int, Field(ge=1, le=12)]
    study_language: Literal["ru", "kk", "en", "other"]
    russian_level: Literal["fluent", "medium", "weak"]
    family_request: Annotated[str, Field(min_length=1, max_length=2000)]
    parent_participates: bool
    contact: Literal["parent", "student"]
    contact_phone: Phone
    manager_comment: Annotated[str, Field(max_length=2000)] | None = None


class BookingIn(BaseModel):
    start: datetime
    handoff: Handoff


class UserRef(BaseModel):
    id: uuid.UUID
    name: str


class ParentOut(BaseModel):
    id: uuid.UUID
    full_name: str | None
    phone: str | None
    email: str | None
    city: str | None
    consent: bool | None
    consent_at: datetime | None


class StudentOut(BaseModel):
    id: uuid.UUID | None = None
    full_name: str | None = None
    age: int | None = None
    gender: str | None = None
    grade: int | None = None
    city: str | None = None
    study_language: str | None = None
    russian_level: str | None = None


class MeetingOut(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    start: datetime
    end: datetime
    # Shown to the owner and the head of sales; a sales manager sees
    # «Специалист (назначен системой)» (ТЗ §3.9 п.8).
    specialist: UserRef | None


class DealCard(BaseModel):
    """A board tile. For the marketer the personal fields are null (ТЗ §2)."""

    id: uuid.UUID
    stage: DealStage
    result: DealResult
    parent_name: str | None
    phone: str | None
    student_name: str | None
    tariff_code: str | None
    total: int | None
    is_target: bool | None
    paid: bool
    consent: bool | None
    manager: UserRef | None
    meeting_start: datetime | None
    closed_at: datetime | None
    created_at: datetime


class DealEventOut(BaseModel):
    id: uuid.UUID
    at: datetime
    actor: UserRef | None
    kind: str
    data: dict[str, Any] | None
    text: str | None


class DealDetail(BaseModel):
    id: uuid.UUID
    stage: DealStage
    result: DealResult
    lost_reason: LostReason | None
    close_comment: str | None
    closed_at: datetime | None
    parent: ParentOut
    student: StudentOut
    manager: UserRef | None
    is_target: bool | None
    non_target_reason: str | None
    tariff_code: str | None
    price: int | None
    discount: int
    total: int | None
    paid_amount: int | None
    paid_at: datetime | None
    payment_method: PaymentMethod | None
    source: str | None
    first_message: str | None
    meeting: MeetingOut | None
    events: list[DealEventOut]
    created_at: datetime


class ParentMatch(BaseModel):
    id: uuid.UUID
    full_name: str
    phone: str | None
    open_deal_id: uuid.UUID | None
