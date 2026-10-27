"""Specialist scheduling (PRO-562, R0 «Календари»). Contract:
docs/frontend-scheduling-api-contract.md.

Schemas only — the router and services land in PRO-512/513/514. Datetimes
are UTC; `date`/`week_start`/`HH:MM` values are Asia/Almaty wall time.
Rule checks that need the clock or the DB (freeze, past, grid bounds,
alignment, overlaps) live in the service, which raises `AppError` with the
contract's `error_code`; only shape limits are declared here.
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

SlotState = Literal["closed", "free", "personal", "booked"]
# `booked` is set by a booking (R2), never through the availability endpoints.
EditableSlotState = Literal["closed", "free", "personal"]
TemplateSlotState = Literal["free", "personal"]
MeetingType = Literal["intro30", "main60"]
MeetingStatus = Literal["pending", "confirmed", "done", "no_show"]

# "HH:MM", Almaty wall time.
WallTime = Annotated[str, Field(max_length=5, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Reason = Annotated[str, Field(min_length=3, max_length=500)]

MAX_CHANGES = 200
MAX_FREE_RANGE_DAYS = 42


class SchedulingConfig(BaseModel):
    timezone: str
    slot_minutes: int
    day_start: WallTime
    day_end: WallTime
    freeze_days: int
    now: datetime
    today: date
    editable_from: date


class SpecialistRef(BaseModel):
    id: uuid.UUID
    full_name: str


class SlotMeeting(BaseModel):
    """Filled for `booked` slots from R2; always null in R0."""

    id: uuid.UUID
    type: MeetingType
    status: MeetingStatus


class Slot(BaseModel):
    start: datetime
    end: datetime
    state: SlotState
    frozen: bool
    past: bool
    meeting: SlotMeeting | None = None


class Day(BaseModel):
    date: date
    frozen: bool
    past: bool
    slots: list[Slot]


class Week(BaseModel):
    specialist: SpecialistRef
    week_start: date
    published: bool
    published_at: datetime | None
    days: list[Day]


class AvailabilityChange(BaseModel):
    start: datetime
    end: datetime
    state: EditableSlotState


class AvailabilityPatch(BaseModel):
    changes: list[AvailabilityChange] = Field(min_length=1, max_length=MAX_CHANGES)
    # Required when the owner edits someone else's schedule; ignored otherwise.
    reason: Reason | None = None


class AvailabilityPatchResponse(BaseModel):
    weeks: list[Week]


class WeekBulkRequest(BaseModel):
    """Body of copy-previous and apply-template."""

    reason: Reason | None = None


class SkippedDay(BaseModel):
    date: date
    error_code: Literal["slot_frozen", "slot_in_past", "slot_booked"]
    count: int


class WeekBulkResponse(BaseModel):
    week: Week
    skipped: list[SkippedDay]


class TemplateInterval(BaseModel):
    start: WallTime
    end: WallTime
    state: TemplateSlotState


# A day has 28 slots, so 28 one-slot intervals is the most a day can hold.
TemplateDay = Annotated[list[TemplateInterval], Field(max_length=28)]


class WeekTemplate(BaseModel):
    # Keys "1"…"7" = Monday…Sunday.
    days: dict[Literal["1", "2", "3", "4", "5", "6", "7"], TemplateDay] = Field(max_length=7)


class WeekTemplateResponse(WeekTemplate):
    updated_at: datetime | None


class SlotConflict(BaseModel):
    start: datetime
    error_code: str


class SchedulingErrorBody(BaseModel):
    """409/422 body for slot-rule violations: AppError's body plus conflicts."""

    detail: str
    error_code: str
    conflicts: list[SlotConflict] = []


class SpecialistWeekStatus(BaseModel):
    id: uuid.UUID
    full_name: str
    week_published: bool
    published_at: datetime | None
    free_slots: int


class SpecialistListResponse(BaseModel):
    week_start: date
    items: list[SpecialistWeekStatus]


class FreeSlotManager(BaseModel):
    start: datetime
    end: datetime
    free_count: int


class FreeSlot(FreeSlotManager):
    specialists: list[SpecialistRef]


class _FreeSlotsBase(BaseModel):
    from_: date = Field(alias="from")
    to: date
    duration: Literal[30, 60]

    model_config = {"populate_by_name": True}


class FreeSlotsManagerResponse(_FreeSlotsBase):
    """`sales_manager`: no specialist names or ids anywhere (ТЗ §3.9 п.8, П1-08)."""

    slots: list[FreeSlotManager]


class FreeSlotsResponse(_FreeSlotsBase):
    """`owner` and `sales_head`: each slot lists the free specialists."""

    slots: list[FreeSlot]


class SchedulingSettings(BaseModel):
    week_reminder_weekday: int = Field(ge=1, le=7)
    week_reminder_time: WallTime
