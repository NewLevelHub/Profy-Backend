"""Specialist schedule — one store for the specialist cabinet and the CRM
(PRO-513/514). Contract: docs/frontend-scheduling-api-contract.md.

Mounted at `/api/v1/scheduling`. A specialist works on their own schedule as
`me`; the owner works on anyone's by id. Every other role only reads the
free-time overview, and a sales manager sees it without names (ТЗ §3.9 п.8).
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.i18n.catalog import key as i18n_key
from app.models.user import User, UserRole
from app.schemas import scheduling as schemas
from app.models.scheduling import MeetingStatus
from app.services.crm import meetings as crm_meetings
from app.services.scheduling import service

router = APIRouter(tags=["scheduling"])

_require_schedule_editor = require_role(UserRole.psychologist, UserRole.owner)
_require_free_viewer = require_role(UserRole.owner, UserRole.sales_head, UserRole.sales_manager)
_require_any_scheduling_role = require_role(
    UserRole.psychologist, UserRole.owner, UserRole.sales_head, UserRole.sales_manager
)
_require_specialists_viewer = require_role(UserRole.owner, UserRole.sales_head)
_require_owner = require_role(UserRole.owner)

_SPECIALIST = "/specialists/{specialist_ref}"


async def _specialist(
    specialist_ref: str,
    current_user: User = Depends(_require_schedule_editor),
    db: AsyncSession = Depends(get_db),
) -> User:
    """The specialist whose schedule is addressed: `me` for the specialist
    themself, an id for the owner. Someone else's id from a specialist is a
    404, not a 403, so ids cannot be probed (as with psychologist notes)."""
    not_found = service.scheduling_error(status.HTTP_404_NOT_FOUND, "specialist_not_found")
    if current_user.role == UserRole.psychologist:
        if specialist_ref == "me" or specialist_ref == str(current_user.id):
            return current_user
        raise not_found
    try:
        specialist_id = uuid.UUID(specialist_ref)
    except ValueError:
        raise not_found from None
    specialist = await service.find_specialist(db, specialist_id)
    if specialist is None:
        raise not_found
    return specialist


@router.get("/config", response_model=schemas.SchedulingConfig)
async def get_config(_: User = Depends(_require_any_scheduling_role)) -> schemas.SchedulingConfig:
    return service.config()


@router.get("/specialists", response_model=schemas.SpecialistListResponse)
async def list_specialists(
    week_start: date | None = Query(default=None),
    _: User = Depends(_require_specialists_viewer),
    db: AsyncSession = Depends(get_db),
) -> schemas.SpecialistListResponse:
    return await service.list_specialists(db, week_start)


@router.get(_SPECIALIST + "/weeks/{week_start}", response_model=schemas.Week)
async def get_week(
    week_start: date,
    specialist: User = Depends(_specialist),
    db: AsyncSession = Depends(get_db),
) -> schemas.Week:
    return await service.get_week(db, specialist, week_start)


@router.patch(_SPECIALIST + "/availability", response_model=schemas.AvailabilityPatchResponse)
async def patch_availability(
    body: schemas.AvailabilityPatch,
    specialist: User = Depends(_specialist),
    current_user: User = Depends(_require_schedule_editor),
    db: AsyncSession = Depends(get_db),
) -> schemas.AvailabilityPatchResponse:
    return await service.patch_availability(db, current_user, specialist, body)


@router.post(_SPECIALIST + "/weeks/{week_start}/copy-previous", response_model=schemas.WeekBulkResponse)
async def copy_previous_week(
    week_start: date,
    body: schemas.WeekBulkRequest,
    specialist: User = Depends(_specialist),
    current_user: User = Depends(_require_schedule_editor),
    db: AsyncSession = Depends(get_db),
) -> schemas.WeekBulkResponse:
    return await service.copy_previous_week(db, current_user, specialist, week_start, body.reason)


@router.get(_SPECIALIST + "/template", response_model=schemas.WeekTemplateResponse)
async def get_template(
    specialist: User = Depends(_specialist),
    db: AsyncSession = Depends(get_db),
) -> schemas.WeekTemplateResponse:
    return await service.get_template(db, specialist)


@router.put(_SPECIALIST + "/template", response_model=schemas.WeekTemplateResponse)
async def put_template(
    body: schemas.WeekTemplate,
    specialist: User = Depends(_specialist),
    current_user: User = Depends(_require_schedule_editor),
    db: AsyncSession = Depends(get_db),
) -> schemas.WeekTemplateResponse:
    return await service.put_template(db, current_user, specialist, body)


@router.post(_SPECIALIST + "/weeks/{week_start}/apply-template", response_model=schemas.WeekBulkResponse)
async def apply_template(
    week_start: date,
    body: schemas.WeekBulkRequest,
    specialist: User = Depends(_specialist),
    current_user: User = Depends(_require_schedule_editor),
    db: AsyncSession = Depends(get_db),
) -> schemas.WeekBulkResponse:
    return await service.apply_template(db, current_user, specialist, week_start, body.reason)


@router.post(_SPECIALIST + "/weeks/{week_start}/publish", response_model=schemas.Week)
async def publish_week(
    week_start: date,
    specialist: User = Depends(_specialist),
    current_user: User = Depends(_require_schedule_editor),
    db: AsyncSession = Depends(get_db),
) -> schemas.Week:
    return await service.publish_week(db, current_user, specialist, week_start)


@router.get(_SPECIALIST + "/meetings", response_model=list[schemas.SpecialistMeeting])
async def list_meetings(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    specialist: User = Depends(_specialist),
    db: AsyncSession = Depends(get_db),
) -> list[schemas.SpecialistMeeting]:
    return await service.list_meetings(db, specialist, date_from, date_to)


@router.post(_SPECIALIST + "/meetings/{meeting_id}/status", response_model=schemas.SpecialistMeeting)
async def set_meeting_status(
    meeting_id: uuid.UUID,
    body: schemas.SpecialistMeetingStatusIn,
    specialist: User = Depends(_specialist),
    current_user: User = Depends(_require_schedule_editor),
    db: AsyncSession = Depends(get_db),
) -> schemas.SpecialistMeeting:
    """The specialist marks their call (ТЗ §4.5): «Подтвердил», and after the
    start «Проведена» or «Не пришёл»."""
    meeting = await crm_meetings.get_meeting(db, current_user, meeting_id, for_update=True)
    if meeting.specialist_id != specialist.id:
        raise service.scheduling_error(status.HTTP_404_NOT_FOUND, "meeting_not_found")
    await crm_meetings.set_status(db, current_user, meeting, MeetingStatus(body.status))
    return schemas.SpecialistMeeting(
        id=meeting.id, type=meeting.type, status=meeting.status, start=meeting.start_at, end=meeting.end_at,
        handoff=meeting.handoff,
    )


@router.get(
    "/free",
    response_model=schemas.FreeSlotsResponse | schemas.FreeSlotsManagerResponse,
    response_model_by_alias=True,
)
async def free_slots(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    duration: int = Query(default=30),
    specialist_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(_require_free_viewer),
    db: AsyncSession = Depends(get_db),
) -> schemas.FreeSlotsResponse | schemas.FreeSlotsManagerResponse:
    if specialist_id is not None and current_user.role not in service.NAMED_FREE_VIEW_ROLES:
        # Filtering by specialist would reveal who is free when.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=i18n_key("api_errors", "insufficient_role", locale="ru"),
        )
    return await service.free_slots(db, current_user, date_from, date_to, duration, specialist_id)


@router.get("/settings", response_model=schemas.SchedulingSettings)
async def get_settings(
    _: User = Depends(_require_owner),
    db: AsyncSession = Depends(get_db),
) -> schemas.SchedulingSettings:
    return await service.get_settings(db)


@router.put("/settings", response_model=schemas.SchedulingSettings)
async def put_settings(
    body: schemas.SchedulingSettings,
    current_user: User = Depends(_require_owner),
    db: AsyncSession = Depends(get_db),
) -> schemas.SchedulingSettings:
    return await service.put_settings(db, current_user, body)
