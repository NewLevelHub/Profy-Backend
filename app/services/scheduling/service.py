"""Specialist availability and free time (PRO-513, PRO-514).

Contract: docs/frontend-scheduling-api-contract.md. The router resolves who
may act on which specialist; this module applies the schedule rules
(freeze, past, grid) and writes the change journal.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timedelta

from fastapi import status
from sqlalchemy import and_, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.i18n.catalog import key as i18n_key
from app.models.scheduling import (
    SchedulingSettings as SettingsRow,
    SlotState,
    SpecialistSlot,
    SpecialistWeekPublication,
    SpecialistWeekTemplate,
)
from app.models.user import User, UserRole
from app.schemas import scheduling as schemas
from app.services import audit, tz
from app.services.scheduling import grid

# Roles that see specialists' names in the free-time overview (ТЗ §2, §9.4).
NAMED_FREE_VIEW_ROLES = (UserRole.owner, UserRole.sales_head)
_SETTINGS_ID = 1


def scheduling_error(
    status_code: int,
    error_code: str,
    *,
    conflicts: list[tuple[datetime, str]] | None = None,
    **params: object,
) -> AppError:
    extra = None
    if conflicts is not None:
        extra = {
            "conflicts": [
                {"start": start.isoformat().replace("+00:00", "Z"), "error_code": code}
                for start, code in conflicts
            ]
        }
    return AppError(
        status_code=status_code,
        error_code=error_code,
        detail=i18n_key("api_errors", error_code).format(**params),
        extra=extra,
    )


def display_name(user: User) -> str:
    return user.full_name or user.email


def ensure_monday(week_start: date) -> None:
    if week_start.weekday() != 0:
        raise scheduling_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "week_start_not_monday")


def require_reason(actor: User, specialist: User, reason: str | None) -> None:
    """Anyone editing someone else's schedule (the owner) must say why."""
    if actor.id != specialist.id and not reason:
        raise scheduling_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "reason_required")


# ── config ──────────────────────────────────────────────────────────────────


def config(now: datetime | None = None) -> schemas.SchedulingConfig:
    now = now or tz.now_utc()
    return schemas.SchedulingConfig(
        timezone=tz.BUSINESS_TIMEZONE,
        slot_minutes=int(grid.SLOT.total_seconds() // 60),
        day_start=grid.DAY_START.strftime("%H:%M"),
        day_end=grid.DAY_END.strftime("%H:%M"),
        freeze_days=tz.FREEZE_DAYS,
        now=now,
        today=tz.today(now),
        editable_from=tz.editable_from(now),
    )


# ── reading a week ──────────────────────────────────────────────────────────


async def _states(
    db: AsyncSession, specialist_id: uuid.UUID, start: datetime, end: datetime
) -> dict[datetime, SlotState]:
    rows = await db.execute(
        select(SpecialistSlot.start_at, SpecialistSlot.state).where(
            SpecialistSlot.specialist_id == specialist_id,
            SpecialistSlot.start_at >= start,
            SpecialistSlot.start_at < end,
        )
    )
    return {start_at: state for start_at, state in rows.all()}


async def get_week(
    db: AsyncSession, specialist: User, week_start: date, now: datetime | None = None
) -> schemas.Week:
    ensure_monday(week_start)
    now = now or tz.now_utc()
    start, end = grid.week_bounds(week_start)
    states = await _states(db, specialist.id, start, end)
    publication = await db.get(SpecialistWeekPublication, (specialist.id, week_start))

    days = []
    for day in grid.week_days(week_start):
        frozen = tz.is_frozen(day, now)
        slots = [
            schemas.Slot(
                start=slot_start,
                end=slot_start + grid.SLOT,
                state=states[slot_start].value if slot_start in states else "closed",
                frozen=frozen,
                past=slot_start <= now,
            )
            for slot_start in grid.day_slot_starts(day)
        ]
        days.append(
            schemas.Day(date=day, frozen=frozen, past=slots[-1].start <= now, slots=slots)
        )
    return schemas.Week(
        specialist=schemas.SpecialistRef(id=specialist.id, full_name=display_name(specialist)),
        week_start=week_start,
        published=publication is not None,
        published_at=publication.published_at if publication else None,
        days=days,
    )


async def _weeks(
    db: AsyncSession, specialist: User, slot_starts: Iterable[datetime], now: datetime
) -> list[schemas.Week]:
    mondays = sorted({tz.week_start(tz.business_date(start)) for start in slot_starts})
    return [await get_week(db, specialist, monday, now) for monday in mondays]


# ── changing availability ───────────────────────────────────────────────────


def _blocker(actor: User, specialist: User, slot_start: datetime, now: datetime) -> str | None:
    """Why `actor` may not change this slot of `specialist`, or None."""
    if slot_start <= now:
        return "slot_in_past"
    # The owner may change frozen days (ТЗ §4.6 п.7); the specialist may not.
    if actor.id == specialist.id and tz.is_frozen(tz.business_date(slot_start), now):
        return "slot_frozen"
    return None


async def _apply(
    db: AsyncSession,
    actor: User,
    specialist: User,
    target: dict[datetime, SlotState | None],
    *,
    action: str,
    reason: str | None,
) -> None:
    """Write `target` (slot → state, None = closed) and journal the diff."""
    if not target:
        return
    current = await _states(db, specialist.id, min(target), max(target) + grid.SLOT)
    changed = {
        slot: state for slot, state in target.items() if current.get(slot) != state
    }
    if not changed:
        return

    to_close = [slot for slot, state in changed.items() if state is None]
    if to_close:
        await db.execute(
            delete(SpecialistSlot).where(
                SpecialistSlot.specialist_id == specialist.id,
                SpecialistSlot.start_at.in_(to_close),
            )
        )
    to_open = [
        {"specialist_id": specialist.id, "start_at": slot, "state": state, "updated_by": actor.id}
        for slot, state in changed.items()
        if state is not None
    ]
    if to_open:
        upsert = insert(SpecialistSlot).values(to_open)
        await db.execute(
            upsert.on_conflict_do_update(
                index_elements=[SpecialistSlot.specialist_id, SpecialistSlot.start_at],
                set_={
                    "state": upsert.excluded.state,
                    "updated_by": upsert.excluded.updated_by,
                    "updated_at": func.now(),
                },
            )
        )

    def _encode(slot: datetime) -> str:
        return slot.isoformat().replace("+00:00", "Z")

    audit.record(
        db,
        actor=actor,
        action=action,
        entity_type="specialist_schedule",
        entity_id=specialist.id,
        before={_encode(slot): (current[slot].value if slot in current else "closed") for slot in changed},
        after={_encode(slot): (state.value if state else "closed") for slot, state in changed.items()},
        reason=reason if actor.id != specialist.id else None,
    )


def _state(value: str) -> SlotState | None:
    return None if value == "closed" else SlotState(value)


async def patch_availability(
    db: AsyncSession,
    actor: User,
    specialist: User,
    body: schemas.AvailabilityPatch,
    now: datetime | None = None,
) -> schemas.AvailabilityPatchResponse:
    now = now or tz.now_utc()
    require_reason(actor, specialist, body.reason)

    target: dict[datetime, SlotState | None] = {}
    for change in body.changes:
        try:
            slots = grid.interval_slots(change.start, change.end)
        except grid.GridError as error:
            raise scheduling_error(status.HTTP_422_UNPROCESSABLE_ENTITY, error.error_code) from None
        for slot in slots:
            if slot in target:
                raise scheduling_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "changes_overlap")
            target[slot] = _state(change.state)

    conflicts = [
        (slot, code) for slot in sorted(target) if (code := _blocker(actor, specialist, slot, now))
    ]
    if conflicts:
        # Past wins over frozen: it cannot be fixed by anyone.
        codes = {code for _, code in conflicts}
        error_code = "slot_in_past" if "slot_in_past" in codes else "slot_frozen"
        raise scheduling_error(status.HTTP_409_CONFLICT, error_code, conflicts=conflicts)

    await _apply(
        db, actor, specialist, target, action="schedule.availability_changed", reason=body.reason
    )
    await db.commit()
    return schemas.AvailabilityPatchResponse(weeks=await _weeks(db, specialist, target, now))


async def _fill_week(
    db: AsyncSession,
    actor: User,
    specialist: User,
    week_start: date,
    desired: dict[datetime, SlotState | None],
    *,
    action: str,
    reason: str | None,
    now: datetime,
) -> schemas.WeekBulkResponse:
    """Set every grid slot of the week to `desired` (missing = closed),
    skipping slots the actor may not change."""
    target: dict[datetime, SlotState | None] = {}
    skipped: dict[tuple[date, str], int] = defaultdict(int)
    for day in grid.week_days(week_start):
        for slot in grid.day_slot_starts(day):
            if code := _blocker(actor, specialist, slot, now):
                skipped[(day, code)] += 1
            else:
                target[slot] = desired.get(slot)
    await _apply(db, actor, specialist, target, action=action, reason=reason)
    await db.commit()
    return schemas.WeekBulkResponse(
        week=await get_week(db, specialist, week_start, now),
        skipped=[
            schemas.SkippedDay(date=day, error_code=code, count=count)
            for (day, code), count in sorted(skipped.items())
        ],
    )


async def copy_previous_week(
    db: AsyncSession,
    actor: User,
    specialist: User,
    week_start: date,
    reason: str | None,
    now: datetime | None = None,
) -> schemas.WeekBulkResponse:
    ensure_monday(week_start)
    require_reason(actor, specialist, reason)
    now = now or tz.now_utc()
    previous = week_start - timedelta(days=grid.WEEK_DAYS)
    start, end = grid.week_bounds(previous)
    source = await _states(db, specialist.id, start, end)
    # Same wall time a week later: Almaty has no DST, so +7 days is exact.
    desired = {slot + timedelta(days=grid.WEEK_DAYS): state for slot, state in source.items()}
    return await _fill_week(
        db, actor, specialist, week_start, desired,
        action="schedule.week_copied", reason=reason, now=now,
    )


# ── template ────────────────────────────────────────────────────────────────

_EMPTY_TEMPLATE_DAYS: dict[str, list] = {str(n): [] for n in range(1, grid.WEEK_DAYS + 1)}


async def get_template(db: AsyncSession, specialist: User) -> schemas.WeekTemplateResponse:
    row = await db.get(SpecialistWeekTemplate, specialist.id)
    if row is None:
        return schemas.WeekTemplateResponse(days=_EMPTY_TEMPLATE_DAYS, updated_at=None)
    return schemas.WeekTemplateResponse(days=row.days, updated_at=row.updated_at)


def _template_slots(
    days: dict[str, list[schemas.TemplateInterval]], week_start: date
) -> dict[datetime, SlotState]:
    """The template laid over the week starting `week_start`."""
    desired: dict[datetime, SlotState] = {}
    for weekday, intervals in days.items():
        day = week_start + timedelta(days=int(weekday) - 1)
        for interval in intervals:
            slots = grid.wall_interval_slots(
                day, grid.parse_wall(interval.start), grid.parse_wall(interval.end)
            )
            for slot in slots:
                if slot in desired:
                    raise grid.GridError("changes_overlap")
                desired[slot] = SlotState(interval.state)
    return desired


async def put_template(
    db: AsyncSession, actor: User, specialist: User, body: schemas.WeekTemplate
) -> schemas.WeekTemplateResponse:
    days = {**_EMPTY_TEMPLATE_DAYS, **body.days}
    try:
        # Validated against an arbitrary Monday: only wall times matter.
        _template_slots(days, tz.week_start(tz.today()))
    except grid.GridError as error:
        raise scheduling_error(status.HTTP_422_UNPROCESSABLE_ENTITY, error.error_code) from None
    stored = {
        weekday: [interval.model_dump() for interval in intervals]
        for weekday, intervals in sorted(days.items())
    }
    upsert = insert(SpecialistWeekTemplate).values(specialist_id=specialist.id, days=stored)
    await db.execute(
        upsert.on_conflict_do_update(
            index_elements=[SpecialistWeekTemplate.specialist_id],
            set_={"days": upsert.excluded.days, "updated_at": func.now()},
        )
    )
    await db.commit()
    row = await db.get(SpecialistWeekTemplate, specialist.id)
    await db.refresh(row)
    return schemas.WeekTemplateResponse(days=row.days, updated_at=row.updated_at)


async def apply_template(
    db: AsyncSession,
    actor: User,
    specialist: User,
    week_start: date,
    reason: str | None,
    now: datetime | None = None,
) -> schemas.WeekBulkResponse:
    ensure_monday(week_start)
    require_reason(actor, specialist, reason)
    now = now or tz.now_utc()
    template = await get_template(db, specialist)
    if not any(template.days.values()):
        raise scheduling_error(status.HTTP_409_CONFLICT, "template_empty")
    desired = _template_slots(template.days, week_start)
    return await _fill_week(
        db, actor, specialist, week_start, desired,
        action="schedule.template_applied", reason=reason, now=now,
    )


# ── publishing a week ───────────────────────────────────────────────────────


async def publish_week(
    db: AsyncSession, actor: User, specialist: User, week_start: date, now: datetime | None = None
) -> schemas.Week:
    ensure_monday(week_start)
    now = now or tz.now_utc()
    if grid.week_bounds(week_start)[1] <= now:
        raise scheduling_error(status.HTTP_409_CONFLICT, "slot_in_past")
    result = await db.execute(
        insert(SpecialistWeekPublication)
        .values(specialist_id=specialist.id, week_start=week_start, published_by=actor.id)
        .on_conflict_do_nothing()
        .returning(SpecialistWeekPublication.week_start)
    )
    if result.first() is not None:
        audit.record(
            db,
            actor=actor,
            action="schedule.week_published",
            entity_type="specialist_schedule",
            entity_id=specialist.id,
            after={"week_start": week_start.isoformat()},
        )
    await db.commit()
    return await get_week(db, specialist, week_start, now)


# ── specialists list ────────────────────────────────────────────────────────


async def active_specialists(db: AsyncSession) -> list[User]:
    rows = await db.execute(
        select(User)
        .where(User.role == UserRole.psychologist, User.is_active.is_(True))
        .order_by(User.full_name.asc().nulls_last(), User.email)
    )
    return list(rows.scalars())


async def find_specialist(db: AsyncSession, specialist_id: uuid.UUID) -> User | None:
    user = await db.get(User, specialist_id)
    if user is None or user.role != UserRole.psychologist or not user.is_active:
        return None
    return user


async def list_specialists(
    db: AsyncSession, week_start: date | None, now: datetime | None = None
) -> schemas.SpecialistListResponse:
    now = now or tz.now_utc()
    week_start = week_start or tz.week_start(tz.today(now)) + timedelta(days=grid.WEEK_DAYS)
    ensure_monday(week_start)
    start, end = grid.week_bounds(week_start)
    specialists = await active_specialists(db)

    free_counts = dict(
        (
            await db.execute(
                select(SpecialistSlot.specialist_id, func.count())
                .where(
                    SpecialistSlot.state == SlotState.free,
                    SpecialistSlot.start_at >= start,
                    SpecialistSlot.start_at < end,
                )
                .group_by(SpecialistSlot.specialist_id)
            )
        ).all()
    )
    published = dict(
        (
            await db.execute(
                select(SpecialistWeekPublication.specialist_id, SpecialistWeekPublication.published_at)
                .where(SpecialistWeekPublication.week_start == week_start)
            )
        ).all()
    )
    return schemas.SpecialistListResponse(
        week_start=week_start,
        items=[
            schemas.SpecialistWeekStatus(
                id=user.id,
                full_name=display_name(user),
                week_published=user.id in published,
                published_at=published.get(user.id),
                free_slots=free_counts.get(user.id, 0),
            )
            for user in specialists
        ],
    )


# ── free time for the CRM ───────────────────────────────────────────────────


async def free_slots(
    db: AsyncSession,
    viewer: User,
    date_from: date,
    date_to: date,
    duration: int,
    specialist_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> schemas.FreeSlotsResponse | schemas.FreeSlotsManagerResponse:
    if duration not in (30, 60):
        raise scheduling_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "duration_invalid")
    if date_to < date_from or (date_to - date_from).days + 1 > schemas.MAX_FREE_RANGE_DAYS:
        raise scheduling_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "range_invalid",
            max_days=schemas.MAX_FREE_RANGE_DAYS,
        )
    now = now or tz.now_utc()
    start = max(tz.day_bounds(date_from)[0], now)
    end = tz.day_bounds(date_to)[1]

    conditions = [
        SpecialistSlot.state == SlotState.free,
        SpecialistSlot.start_at > now,
        SpecialistSlot.start_at >= start,
        SpecialistSlot.start_at < end,
        User.role == UserRole.psychologist,
        User.is_active.is_(True),
    ]
    if specialist_id is not None:
        conditions.append(SpecialistSlot.specialist_id == specialist_id)
    rows = await db.execute(
        select(SpecialistSlot.specialist_id, SpecialistSlot.start_at, User.full_name, User.email)
        .join(User, and_(User.id == SpecialistSlot.specialist_id))
        .where(*conditions)
    )

    by_specialist: dict[uuid.UUID, set[datetime]] = defaultdict(set)
    names: dict[uuid.UUID, str] = {}
    for spec_id, slot_start, full_name, email in rows.all():
        by_specialist[spec_id].add(slot_start)
        names[spec_id] = full_name or email

    window = timedelta(minutes=duration)
    free_at: dict[datetime, list[uuid.UUID]] = defaultdict(list)
    for spec_id, starts in by_specialist.items():
        for slot_start in starts:
            # 60 minutes need the next slot of the same specialist free too.
            if duration == 60 and slot_start + grid.SLOT not in starts:
                continue
            free_at[slot_start].append(spec_id)

    ordered = sorted(free_at.items())
    common = {"from": date_from, "to": date_to, "duration": duration}
    if viewer.role in NAMED_FREE_VIEW_ROLES:
        return schemas.FreeSlotsResponse(
            **common,
            slots=[
                schemas.FreeSlot(
                    start=slot_start,
                    end=slot_start + window,
                    free_count=len(spec_ids),
                    specialists=sorted(
                        (schemas.SpecialistRef(id=spec_id, full_name=names[spec_id]) for spec_id in spec_ids),
                        key=lambda ref: ref.full_name,
                    ),
                )
                for slot_start, spec_ids in ordered
            ],
        )
    return schemas.FreeSlotsManagerResponse(
        **common,
        slots=[
            schemas.FreeSlotManager(start=slot_start, end=slot_start + window, free_count=len(spec_ids))
            for slot_start, spec_ids in ordered
        ],
    )


# ── settings ────────────────────────────────────────────────────────────────


async def _settings_row(db: AsyncSession) -> SettingsRow:
    row = await db.get(SettingsRow, _SETTINGS_ID)
    if row is None:
        # Seeded by the migration; recreated here if someone removed it.
        row = SettingsRow(id=_SETTINGS_ID)
        db.add(row)
        await db.flush()
        await db.refresh(row)
    return row


async def get_settings(db: AsyncSession) -> schemas.SchedulingSettings:
    row = await _settings_row(db)
    return schemas.SchedulingSettings(
        week_reminder_weekday=row.week_reminder_weekday,
        week_reminder_time=row.week_reminder_time.strftime("%H:%M"),
    )


async def put_settings(
    db: AsyncSession, actor: User, body: schemas.SchedulingSettings
) -> schemas.SchedulingSettings:
    reminder_time = grid.parse_wall(body.week_reminder_time)
    if not grid.wall_on_grid(reminder_time):
        raise scheduling_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "slot_misaligned")
    row = await _settings_row(db)
    before = await get_settings(db)
    row.week_reminder_weekday = body.week_reminder_weekday
    row.week_reminder_time = reminder_time
    row.updated_by = actor.id
    audit.record(
        db,
        actor=actor,
        action="schedule.settings_changed",
        entity_type="scheduling_settings",
        entity_id=_SETTINGS_ID,
        before=before.model_dump(),
        after=body.model_dump(),
    )
    await db.commit()
    return await get_settings(db)
