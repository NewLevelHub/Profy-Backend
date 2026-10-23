"""CRM deals board and booking. Contract: docs/frontend-crm-api-contract.md."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.models.crm import DealResult, DealStage, LostReason, PaymentMethod, TaskType

Name = Annotated[str, Field(min_length=1, max_length=255)]
ShortText = Annotated[str, Field(max_length=255)]
LongText = Annotated[str, Field(max_length=4000)]
Phone = Annotated[str, Field(max_length=32)]


class TariffItem(BaseModel):
    code: str
    name: str
    price: int
    description: str | None
    psychologist_review: bool
    active: bool


TariffName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
TariffPrice = Annotated[int, Field(ge=0, le=100_000_000)]
TariffDescription = Annotated[str, Field(max_length=1000)]


class TariffIn(BaseModel):
    name: TariffName
    price: TariffPrice
    description: TariffDescription | None = None
    psychologist_review: bool = True


class TariffPatch(BaseModel):
    name: TariffName | None = None
    price: TariffPrice | None = None
    description: TariffDescription | None = None
    psychologist_review: bool | None = None
    active: bool | None = None


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


class DealFilters(BaseModel):
    """Board and list filters (ТЗ §1.5). `manager` is a user id or `none`
    for the unassigned inbox."""

    q: Annotated[str, Field(max_length=100)] | None = None
    stage: DealStage | None = None
    tariff: Annotated[str, Field(max_length=32)] | None = None
    manager: Annotated[str, Field(pattern=r"^(none|[0-9a-fA-F-]{36})$")] | None = None
    paid: bool | None = None
    created_from: date | None = None
    created_to: date | None = None


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


class StudentAccountOut(BaseModel):
    """The student's Profile account (ТЗ §4.4). `invite_url` is the open
    one-time link, null once used or before one is made."""

    linked: bool
    email: str | None
    invite_url: str | None
    invite_created_at: datetime | None


class StudentLinkIn(BaseModel):
    # Looked up as typed (trimmed, lower-cased), not validated: it only has
    # to match an existing account.
    email: str = Field(min_length=3, max_length=320)


class StudentInviteAcceptIn(BaseModel):
    token: str = Field(min_length=16, max_length=128)


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
    source: str | None = None
    is_target: bool | None
    paid: bool
    consent: bool | None
    manager: UserRef | None
    meeting_start: datetime | None
    # Due time of the nearest open task; null = «Нет задач».
    next_task_due: datetime | None = None
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
    # Fixed with the price: the report waits for a psychologist (True) or
    # goes to the student at once (False); None — no tariff yet.
    psychologist_review: bool | None
    discount: int
    total: int | None
    paid_amount: int | None
    paid_at: datetime | None
    payment_method: PaymentMethod | None
    source: str | None
    first_message: str | None
    # When the deal came to its current stage.
    stage_at: datetime
    # The first call (the one the manager booked).
    meeting: MeetingOut | None
    # Every live call: the first and the specialist's second, by time.
    meetings: list[MeetingOut]
    student_account: StudentAccountOut
    tasks: list["TaskOut"] = []
    events: list[DealEventOut]
    created_at: datetime


class ParentMatch(BaseModel):
    id: uuid.UUID
    full_name: str
    phone: str | None
    open_deal_id: uuid.UUID | None


# ── meetings (ТЗ §3.9, §4.5) ────────────────────────────────────────────────

Reason = Annotated[str, Field(min_length=3, max_length=1000)]


class CalendarMeeting(BaseModel):
    """A booked call on the CRM calendar. `specialist` only for the owner and
    the head of sales; a sales manager sees the calls of their own deals."""

    id: uuid.UUID
    deal_id: uuid.UUID | None
    type: str
    status: str
    start: datetime
    end: datetime
    student_name: str | None
    parent_name: str | None = None
    specialist: UserRef | None
    # The caller's own deal. For a sales manager every other call comes as
    # «Занято»: no deal, no names.
    mine: bool = False


class MeetingHistoryItem(BaseModel):
    at: datetime
    actor: UserRef | None
    actor_role: str
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason: str | None


class MeetingDetail(CalendarMeeting):
    handoff: dict[str, Any]
    cancel_reason: str | None
    rescheduled_from_id: uuid.UUID | None
    # "first" — booked by the manager; "second" — the report review the
    # specialist set; null — no deal.
    call: Literal["first", "second"] | None
    # The requesting user may move or cancel it now (§10).
    can_move: bool
    history: list[MeetingHistoryItem]


class MeetingStatusIn(BaseModel):
    status: Literal["confirmed", "done", "no_show"]


class MeetingCancelIn(BaseModel):
    reason: Reason


class MeetingRescheduleIn(BaseModel):
    start: datetime
    reason: Reason


class RescheduleRequestIn(BaseModel):
    comment: Reason


# ── tasks (ТЗ §3.11) ────────────────────────────────────────────────────────


class TaskIn(BaseModel):
    type: TaskType = TaskType.call
    text: Annotated[str, Field(min_length=1, max_length=2000)]
    due_at: datetime
    # Empty = yourself. A sales manager may only pick themself.
    assignee_id: uuid.UUID | None = None


class TaskCreate(TaskIn):
    deal_id: uuid.UUID | None = None


class TaskPatch(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=2000)] | None = None
    due_at: datetime | None = None
    assignee_id: uuid.UUID | None = None


class TaskDoneIn(BaseModel):
    result: Annotated[str, Field(max_length=2000)] | None = None


class TaskOut(BaseModel):
    id: uuid.UUID
    deal_id: uuid.UUID | None
    # «Родитель · ученик» of the deal, for the task list.
    deal_title: str | None
    type: TaskType
    text: str
    due_at: datetime
    done_at: datetime | None
    result: str | None
    assignee: UserRef | None
    created_by: UserRef | None
    created_at: datetime


class StaffMember(BaseModel):
    """«Сотрудники» in the CRM: the owner's view of the business staff."""

    id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime


class SalesUser(BaseModel):
    id: uuid.UUID
    name: str
    role: str


DealDetail.model_rebuild()


class ClientRow(BaseModel):
    """«Клиенты» (ТЗ §3.2): a parent with their children, deals and calls."""

    id: uuid.UUID
    full_name: str
    phone: str | None
    city: str | None
    students: list[str]
    deals: int
    open_deal_id: uuid.UUID | None
    meetings_done: int
    meetings_total: int
    no_shows: int
    paid_total: int
