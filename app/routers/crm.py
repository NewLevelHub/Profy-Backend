"""CRM deals board and booking (ТЗ CRM Profile v4.1 part 1). Contract:
docs/frontend-crm-api-contract.md.

Mounted at `/api/v1/crm`. Sales roles only; the marketer reads the board
without personal data and cannot open or change a deal (ТЗ §2).
"""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.user import User, UserRole
from app.schemas import crm as schemas
from app.models.scheduling import MeetingStatus
from app.services.crm import deals, invites, meetings, staff, tariffs, tasks

router = APIRouter(tags=["crm"])

_board_reader = require_role(UserRole.owner, UserRole.sales_head, UserRole.sales_manager, UserRole.marketer)
_seller = require_role(UserRole.owner, UserRole.sales_head, UserRole.sales_manager)
_owner = require_role(UserRole.owner)


async def _detail(db: AsyncSession, user: User, deal_id: uuid.UUID) -> schemas.DealDetail:
    return await deals.detail(db, user, await deals.get_deal(db, user, deal_id))


@router.get("/meta", response_model=schemas.CrmMeta)
async def meta(_: User = Depends(_board_reader), db: AsyncSession = Depends(get_db)) -> schemas.CrmMeta:
    return await deals.meta(db)


@router.get("/staff", response_model=list[schemas.StaffMember])
async def list_staff(_: User = Depends(_owner), db: AsyncSession = Depends(get_db)) -> list[schemas.StaffMember]:
    return await staff.members(db)


@router.post("/tariffs", response_model=schemas.TariffItem, status_code=201)
async def create_tariff(
    body: schemas.TariffIn, user: User = Depends(_owner), db: AsyncSession = Depends(get_db)
) -> schemas.TariffItem:
    return await tariffs.create(db, user, body)


@router.patch("/tariffs/{code}", response_model=schemas.TariffItem)
async def patch_tariff(
    code: str, body: schemas.TariffPatch, user: User = Depends(_owner), db: AsyncSession = Depends(get_db)
) -> schemas.TariffItem:
    return await tariffs.update(db, user, code, body)


@router.get("/deals", response_model=list[schemas.DealCard])
async def list_deals(
    result: Literal["open", "won", "lost", "all"] = Query(default="open"),
    filters: schemas.DealFilters = Depends(),
    user: User = Depends(_board_reader),
    db: AsyncSession = Depends(get_db),
) -> list[schemas.DealCard]:
    return await deals.list_deals(db, user, result, filters)


@router.get("/users", response_model=list[schemas.SalesUser])
async def sales_users(_: User = Depends(_seller), db: AsyncSession = Depends(get_db)) -> list[schemas.SalesUser]:
    """Sales staff, for the assignee and manager pickers."""
    return await tasks.sales_users(db)


@router.post("/deals", response_model=schemas.DealDetail, status_code=201)
async def create_deal(
    body: schemas.DealCreate, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    deal = await deals.create_deal(db, user, body)
    return await _detail(db, user, deal.id)


@router.get("/clients", response_model=list[schemas.ClientRow])
async def list_clients(
    q: str | None = Query(default=None, max_length=100),
    user: User = Depends(_seller),
    db: AsyncSession = Depends(get_db),
) -> list[schemas.ClientRow]:
    return await deals.clients(db, user, q)


@router.get("/parents", response_model=list[schemas.ParentMatch])
async def find_parents(
    phone: str = Query(max_length=32), _: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> list[schemas.ParentMatch]:
    return await deals.find_parents(db, phone)


@router.get("/deals/{deal_id}", response_model=schemas.DealDetail)
async def get_deal(
    deal_id: uuid.UUID, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    return await _detail(db, user, deal_id)


@router.patch("/deals/{deal_id}", response_model=schemas.DealDetail)
async def patch_deal(
    deal_id: uuid.UUID, body: schemas.DealPatch, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    await deals.patch_deal(db, user, deal_id, body)
    return await _detail(db, user, deal_id)


@router.post("/deals/{deal_id}/accept", response_model=schemas.DealDetail)
async def accept(deal_id: uuid.UUID, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)):
    await deals.accept(db, user, deal_id)
    return await _detail(db, user, deal_id)


@router.post("/deals/{deal_id}/stage", response_model=schemas.DealDetail)
async def move(
    deal_id: uuid.UUID, body: schemas.StageMove, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    await deals.move(db, user, deal_id, body.stage)
    return await _detail(db, user, deal_id)


@router.post("/deals/{deal_id}/payment", response_model=schemas.DealDetail)
async def mark_payment(
    deal_id: uuid.UUID, body: schemas.PaymentIn, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    await deals.mark_payment(db, user, deal_id, body)
    return await _detail(db, user, deal_id)


@router.delete("/deals/{deal_id}/payment", response_model=schemas.DealDetail)
async def cancel_payment(
    deal_id: uuid.UUID, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    await deals.cancel_payment(db, user, deal_id)
    return await _detail(db, user, deal_id)


@router.post("/deals/{deal_id}/consent", response_model=schemas.DealDetail)
async def set_consent(
    deal_id: uuid.UUID, body: schemas.ConsentIn, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    await deals.set_consent(db, user, deal_id, body.given)
    return await _detail(db, user, deal_id)


@router.post("/deals/{deal_id}/invite", response_model=schemas.DealDetail)
async def create_invite(
    deal_id: uuid.UUID, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    """A new one-time link for the student; the previous one stops working."""
    await invites.create_invite(db, user, deal_id)
    return await _detail(db, user, deal_id)


@router.post("/deals/{deal_id}/student", response_model=schemas.DealDetail)
async def link_student(
    deal_id: uuid.UUID, body: schemas.StudentLinkIn, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    """The owner or the head of sales ties an existing student account by email."""
    await invites.link_by_email(db, user, deal_id, body.email)
    return await _detail(db, user, deal_id)


@router.post("/deals/{deal_id}/close", response_model=schemas.DealDetail)
async def close(
    deal_id: uuid.UUID, body: schemas.CloseIn, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    await deals.close(db, user, deal_id, body)
    return await _detail(db, user, deal_id)


@router.post("/deals/{deal_id}/notes", response_model=schemas.DealDetail)
async def add_note(
    deal_id: uuid.UUID, body: schemas.NoteIn, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    await deals.add_note(db, user, deal_id, body.text)
    return await _detail(db, user, deal_id)


@router.post("/deals/{deal_id}/booking", response_model=schemas.DealDetail)
async def book(
    deal_id: uuid.UUID, body: schemas.BookingIn, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    await deals.book(db, user, deal_id, body)
    return await _detail(db, user, deal_id)


# ── meetings ────────────────────────────────────────────────────────────────


async def _meeting_detail(db: AsyncSession, user: User, meeting_id: uuid.UUID) -> schemas.MeetingDetail:
    return await meetings.detail(db, user, await meetings.get_meeting(db, user, meeting_id))


@router.get("/meetings", response_model=list[schemas.CalendarMeeting])
async def calendar(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    user: User = Depends(_seller),
    db: AsyncSession = Depends(get_db),
) -> list[schemas.CalendarMeeting]:
    return await meetings.calendar(db, user, date_from, date_to)


@router.get("/meetings/{meeting_id}", response_model=schemas.MeetingDetail)
async def get_meeting(
    meeting_id: uuid.UUID, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.MeetingDetail:
    return await _meeting_detail(db, user, meeting_id)


@router.post("/meetings/{meeting_id}/status", response_model=schemas.MeetingDetail)
async def meeting_status(
    meeting_id: uuid.UUID,
    body: schemas.MeetingStatusIn,
    user: User = Depends(_seller),
    db: AsyncSession = Depends(get_db),
) -> schemas.MeetingDetail:
    meeting = await meetings.get_meeting(db, user, meeting_id, for_update=True)
    await meetings.set_status(db, user, meeting, MeetingStatus(body.status))
    return await _meeting_detail(db, user, meeting_id)


@router.post("/meetings/{meeting_id}/cancel", response_model=schemas.MeetingDetail)
async def cancel_meeting(
    meeting_id: uuid.UUID,
    body: schemas.MeetingCancelIn,
    user: User = Depends(_seller),
    db: AsyncSession = Depends(get_db),
) -> schemas.MeetingDetail:
    meeting = await meetings.get_meeting(db, user, meeting_id, for_update=True)
    await meetings.cancel(db, user, meeting, body.reason.strip())
    return await _meeting_detail(db, user, meeting_id)


@router.post("/meetings/{meeting_id}/reschedule", response_model=schemas.MeetingDetail)
async def reschedule_meeting(
    meeting_id: uuid.UUID,
    body: schemas.MeetingRescheduleIn,
    user: User = Depends(_seller),
    db: AsyncSession = Depends(get_db),
) -> schemas.MeetingDetail:
    """Returns the new call; the old one stays cancelled with the reason."""
    meeting = await meetings.get_meeting(db, user, meeting_id, for_update=True)
    moved = await meetings.reschedule(db, user, meeting, body.start, body.reason.strip())
    return await _meeting_detail(db, user, moved.id)


@router.post("/meetings/{meeting_id}/reschedule-request", response_model=schemas.TaskOut, status_code=201)
async def request_reschedule(
    meeting_id: uuid.UUID,
    body: schemas.RescheduleRequestIn,
    user: User = Depends(_seller),
    db: AsyncSession = Depends(get_db),
) -> schemas.TaskOut:
    meeting = await meetings.get_meeting(db, user, meeting_id)
    task = await tasks.request_reschedule(db, user, meeting, body.comment)
    return (await tasks.task_out(db, [task]))[0]


# ── tasks ───────────────────────────────────────────────────────────────────


@router.get("/tasks", response_model=list[schemas.TaskOut])
async def list_tasks(
    scope: Literal["mine", "all"] = Query(default="mine"),
    state: Literal["open", "done"] = Query(default="open"),
    deal_id: uuid.UUID | None = Query(default=None),
    assignee_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(_seller),
    db: AsyncSession = Depends(get_db),
) -> list[schemas.TaskOut]:
    return await tasks.list_tasks(db, user, scope=scope, state=state, deal_id=deal_id, assignee_id=assignee_id)


@router.post("/tasks", response_model=schemas.TaskOut, status_code=201)
async def create_task(
    body: schemas.TaskCreate, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.TaskOut:
    task = await tasks.create_task(db, user, body)
    return (await tasks.task_out(db, [task]))[0]


@router.patch("/tasks/{task_id}", response_model=schemas.TaskOut)
async def patch_task(
    task_id: uuid.UUID, body: schemas.TaskPatch, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.TaskOut:
    task = await tasks.patch_task(db, user, task_id, body)
    return (await tasks.task_out(db, [task]))[0]


@router.post("/tasks/{task_id}/done", response_model=schemas.TaskOut)
async def complete_task(
    task_id: uuid.UUID, body: schemas.TaskDoneIn, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.TaskOut:
    task = await tasks.complete_task(db, user, task_id, body.result)
    return (await tasks.task_out(db, [task]))[0]
