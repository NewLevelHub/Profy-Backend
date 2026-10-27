"""Deals board (ТЗ CRM Profile v4.1 §3.2–3.10). Contract:
docs/frontend-crm-api-contract.md.

Leads are entered manually and stages 1–6 move by hand. Stages 7–8 and
«Успешно» follow the student's account once it is linked to the deal
(progress.py); until then, and for 9–10, the head of sales or the owner moves
them. The rules of §3.3 that do not
depend on events hold already: a non-target lead stays in qualification,
«Оплачено» comes only from marking the payment, closing needs a reason, and
after payment only the head of sales or the owner closes the deal.
"""

import re
import uuid
from datetime import datetime
from typing import Any

from fastapi import status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.i18n.catalog import key as i18n_key
from app.models.crm import (
    STAGE_ORDER,
    CrmDeal,
    CrmDealEvent,
    CrmParent,
    CrmStudent,
    CrmTariff,
    CrmTask,
    DealResult,
    DealStage,
    LostReason,
)
from app.models.scheduling import Meeting, MeetingStatus
from app.models.user import User, UserRole
from app.schemas import crm as schemas
from app.services import audit, tz
from app.services.crm import progress
from app.services.scheduling import booking

SALES_ROLES = (UserRole.owner, UserRole.sales_head, UserRole.sales_manager, UserRole.marketer)
# Who sees every deal and the specialists' names, and may do what the
# manager may not (ТЗ §2). The owner and the head of sales.
SUPERVISORS = (UserRole.owner, UserRole.sales_head)

# The manager books the first call, always 30 minutes; the 60-minute second
# one the specialist sets (app/services/scheduling/second_meeting.py).
FIRST_CALL_MINUTES = 30

# Feed events that put the deal on its current stage.
STAGE_EVENTS = ("stage", "accepted", "created")

_PAID_INDEX = STAGE_ORDER.index(DealStage.paid)
_QUALIFICATION_INDEX = STAGE_ORDER.index(DealStage.qualification)
_CONSULTATION_INDEX = STAGE_ORDER.index(DealStage.consultation)
_INVOICE_INDEX = STAGE_ORDER.index(DealStage.invoice)


def crm_error(status_code: int, error_code: str, **extra: Any) -> AppError:
    return AppError(
        status_code=status_code,
        error_code=error_code,
        detail=i18n_key("api_errors", error_code),
        extra=extra or None,
    )


def _supervisor(user: User) -> bool:
    return user.role in SUPERVISORS


def normalize_phone(raw: str | None) -> str | None:
    """`+7XXXXXXXXXX` for Kazakh numbers in any common spelling; other
    numbers keep their digits with a leading `+`."""
    if raw is None:
        return None
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if len(digits) == 11 and digits[0] in "78":
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    return "+" + digits


def _user_ref(user: User | None) -> schemas.UserRef | None:
    return schemas.UserRef(id=user.id, name=user.full_name or user.email) if user else None


async def _users(db: AsyncSession, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, User]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    rows = await db.execute(select(User).where(User.id.in_(wanted)))
    return {user.id: user for user in rows.scalars()}


def _event(
    db: AsyncSession, deal: CrmDeal, actor: User, kind: str, data: dict | None = None, text: str | None = None
) -> None:
    db.add(CrmDealEvent(deal_id=deal.id, actor_id=actor.id, kind=kind, data=data, text=text))


# ── access ──────────────────────────────────────────────────────────────────


def _visible_clause(user: User):
    """A sales manager sees their own deals and the unassigned inbox."""
    if user.role == UserRole.sales_manager:
        return or_(CrmDeal.manager_id == user.id, CrmDeal.manager_id.is_(None))
    return None


async def get_deal(db: AsyncSession, user: User, deal_id: uuid.UUID, *, for_update: bool = False) -> CrmDeal:
    """The deal if `user` may open it; someone else's deal is a 404."""
    query = select(CrmDeal).where(CrmDeal.id == deal_id)
    if (clause := _visible_clause(user)) is not None:
        query = query.where(clause)
    if for_update:
        query = query.with_for_update()
    deal = await db.scalar(query)
    if deal is None:
        raise crm_error(status.HTTP_404_NOT_FOUND, "deal_not_found")
    return deal


def _require_owned(user: User, deal: CrmDeal) -> None:
    """Changes need the deal taken: an inbox deal is only accepted first."""
    if user.role == UserRole.sales_manager and deal.manager_id != user.id:
        raise crm_error(status.HTTP_409_CONFLICT, "deal_not_accepted")


def _require_open(deal: CrmDeal) -> None:
    if deal.result == DealResult.lost:
        raise crm_error(status.HTTP_409_CONFLICT, "deal_closed")


# ── meta, list ──────────────────────────────────────────────────────────────


async def meta(db: AsyncSession) -> schemas.CrmMeta:
    # Archived tariffs too: deals that have one still show its name.
    rows = await db.execute(select(CrmTariff).order_by(CrmTariff.sort, CrmTariff.code))
    return schemas.CrmMeta(
        stages=STAGE_ORDER,
        tariffs=[schemas.TariffItem.model_validate(t, from_attributes=True) for t in rows.scalars()],
        lost_reasons=list(LostReason),
    )


async def _active_meetings(db: AsyncSession, deal_ids: list[uuid.UUID]) -> dict[uuid.UUID, Meeting]:
    if not deal_ids:
        return {}
    rows = await db.execute(
        select(Meeting)
        .where(Meeting.deal_id.in_(deal_ids), Meeting.status != MeetingStatus.cancelled)
        .order_by(Meeting.start_at)
    )
    first: dict[uuid.UUID, Meeting] = {}
    for meeting in rows.scalars():
        # The call the manager booked; a later one is the specialist's second.
        first.setdefault(meeting.deal_id, meeting)
    return first


async def list_deals(
    db: AsyncSession, user: User, result: str = "open", filters: schemas.DealFilters | None = None
) -> list[schemas.DealCard]:
    query = select(CrmDeal, CrmParent, CrmStudent).join(CrmParent, CrmParent.id == CrmDeal.parent_id).outerjoin(
        CrmStudent, CrmStudent.id == CrmDeal.student_id
    )
    if (clause := _visible_clause(user)) is not None:
        query = query.where(clause)
    if result != "all":
        query = query.where(CrmDeal.result == DealResult(result))
    if filters is not None:
        query = _apply_filters(query, user, filters)
    rows = (await db.execute(query.order_by(CrmDeal.created_at.desc()))).all()

    users = await _users(db, {deal.manager_id for deal, _, _ in rows})
    meetings = await _active_meetings(db, [deal.id for deal, _, _ in rows])
    tasks = await _next_task_due(db, [deal.id for deal, _, _ in rows])
    # The marketer sees the board without personal data (ТЗ §2, §6.2).
    masked = user.role == UserRole.marketer
    return [
        schemas.DealCard(
            id=deal.id,
            stage=deal.stage,
            result=deal.result,
            parent_name=None if masked else parent.full_name,
            phone=None if masked else parent.phone,
            student_name=None if masked or student is None else student.full_name,
            tariff_code=deal.tariff_code,
            total=deal.total,
            source=deal.source,
            is_target=deal.is_target,
            paid=deal.paid_at is not None,
            consent=parent.consent,
            manager=_user_ref(users.get(deal.manager_id)),
            meeting_start=meetings[deal.id].start_at if deal.id in meetings else None,
            next_task_due=tasks.get(deal.id),
            closed_at=deal.closed_at,
            created_at=deal.created_at,
        )
        for deal, parent, student in rows
    ]


def _apply_filters(query, user: User, f: schemas.DealFilters):
    if f.q and (text := f.q.strip()):
        like = f"%{text}%"
        conditions = [CrmParent.full_name.ilike(like), CrmStudent.full_name.ilike(like)]
        digits = re.sub(r"\D", "", text)
        if len(digits) >= 4:
            conditions.append(CrmParent.phone.like(f"%{digits[-10:]}%"))
        # The marketer cannot look people up by name or phone (ТЗ §2).
        if user.role != UserRole.marketer:
            query = query.where(or_(*conditions))
    if f.stage:
        query = query.where(CrmDeal.stage == f.stage)
    if f.tariff:
        query = query.where(CrmDeal.tariff_code == f.tariff)
    if f.manager == "none":
        query = query.where(CrmDeal.manager_id.is_(None))
    elif f.manager:
        query = query.where(CrmDeal.manager_id == uuid.UUID(f.manager))
    if f.paid is not None:
        query = query.where(CrmDeal.paid_at.is_not(None) if f.paid else CrmDeal.paid_at.is_(None))
    if f.created_from:
        query = query.where(CrmDeal.created_at >= tz.day_bounds(f.created_from)[0])
    if f.created_to:
        query = query.where(CrmDeal.created_at < tz.day_bounds(f.created_to)[1])
    return query


async def _next_task_due(db: AsyncSession, deal_ids: list[uuid.UUID]) -> dict[uuid.UUID, datetime]:
    if not deal_ids:
        return {}
    rows = await db.execute(
        select(CrmTask.deal_id, func.min(CrmTask.due_at))
        .where(CrmTask.deal_id.in_(deal_ids), CrmTask.done_at.is_(None))
        .group_by(CrmTask.deal_id)
    )
    return dict(rows.all())


# ── detail ──────────────────────────────────────────────────────────────────


async def _deal_tasks(db: AsyncSession, deal_id: uuid.UUID) -> list[schemas.TaskOut]:
    from app.services.crm import tasks  # tasks builds on this module

    return await tasks.deal_tasks(db, deal_id)


async def _student_account(db: AsyncSession, deal: CrmDeal) -> schemas.StudentAccountOut:
    from app.services.crm import invites  # invites builds on this module

    return await invites.account_info(db, deal)


async def detail(db: AsyncSession, user: User, deal: CrmDeal) -> schemas.DealDetail:
    parent = await db.get(CrmParent, deal.parent_id)
    student = await db.get(CrmStudent, deal.student_id) if deal.student_id else None
    events = list(
        (
            await db.execute(
                select(CrmDealEvent).where(CrmDealEvent.deal_id == deal.id).order_by(CrmDealEvent.at.desc())
            )
        ).scalars()
    )
    meeting = (await _active_meetings(db, [deal.id])).get(deal.id)
    users = await _users(
        db, {deal.manager_id, meeting.specialist_id if meeting else None, *(e.actor_id for e in events)}
    )
    def meeting_out(m: Meeting) -> schemas.MeetingOut:
        return schemas.MeetingOut(
            id=m.id,
            type=m.type.value,
            status=m.status.value,
            start=m.start_at,
            end=m.end_at,
            # A sales manager never learns who the specialist is (ТЗ §3.9 п.8).
            specialist=_user_ref(users.get(m.specialist_id)) if _supervisor(user) else None,
        )

    calls = (
        await db.execute(
            select(Meeting)
            .where(Meeting.deal_id == deal.id, Meeting.status != MeetingStatus.cancelled)
            .order_by(Meeting.start_at)
        )
    ).scalars().all()
    return schemas.DealDetail(
        id=deal.id,
        stage=deal.stage,
        result=deal.result,
        lost_reason=deal.lost_reason,
        close_comment=deal.close_comment,
        closed_at=deal.closed_at,
        parent=schemas.ParentOut(
            id=parent.id,
            full_name=parent.full_name,
            phone=parent.phone,
            email=parent.email,
            city=parent.city,
            consent=parent.consent,
            consent_at=parent.consent_at,
        ),
        student=schemas.StudentOut(**{f: getattr(student, f) for f in schemas.StudentOut.model_fields})
        if student
        else schemas.StudentOut(),
        manager=_user_ref(users.get(deal.manager_id)),
        is_target=deal.is_target,
        non_target_reason=deal.non_target_reason,
        tariff_code=deal.tariff_code,
        price=deal.price,
        psychologist_review=deal.psychologist_review,
        discount=deal.discount,
        total=deal.total,
        paid_amount=deal.paid_amount,
        paid_at=deal.paid_at,
        payment_method=deal.payment_method,
        source=deal.source,
        first_message=deal.first_message,
        stage_at=next((e.at for e in events if e.kind in STAGE_EVENTS), deal.created_at),
        meeting=meeting_out(meeting) if meeting else None,
        meetings=[meeting_out(m) for m in calls],
        student_account=await _student_account(db, deal),
        tasks=await _deal_tasks(db, deal.id),
        events=[
            schemas.DealEventOut(
                id=e.id, at=e.at, actor=_user_ref(users.get(e.actor_id)), kind=e.kind, data=e.data, text=e.text
            )
            for e in events
        ],
        created_at=deal.created_at,
    )


# ── create, duplicates ──────────────────────────────────────────────────────


async def find_parents(db: AsyncSession, phone: str) -> list[schemas.ParentMatch]:
    normalized = normalize_phone(phone)
    if not normalized:
        return []
    parents = list((await db.execute(select(CrmParent).where(CrmParent.phone == normalized))).scalars())
    matches = []
    for parent in parents:
        open_deal = await db.scalar(
            select(CrmDeal.id).where(CrmDeal.parent_id == parent.id, CrmDeal.result == DealResult.open).limit(1)
        )
        matches.append(
            schemas.ParentMatch(id=parent.id, full_name=parent.full_name, phone=parent.phone, open_deal_id=open_deal)
        )
    return matches


def _apply_student(student: CrmStudent, data: schemas.StudentIn) -> None:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(student, field, value)


async def create_deal(db: AsyncSession, user: User, body: schemas.DealCreate) -> CrmDeal:
    if body.parent_id:
        parent = await db.get(CrmParent, body.parent_id)
        if parent is None:
            raise crm_error(status.HTTP_404_NOT_FOUND, "parent_not_found")
    elif body.parent:
        phone = normalize_phone(body.parent.phone)
        if phone and (existing := await find_parents(db, phone)):
            # ТЗ §3.2: warn about the duplicate; the UI offers to add the deal
            # to the existing client instead.
            raise crm_error(
                status.HTTP_409_CONFLICT,
                "parent_exists",
                parent_id=str(existing[0].id),
                open_deal_id=str(existing[0].open_deal_id) if existing[0].open_deal_id else None,
            )
        parent = CrmParent(
            full_name=body.parent.full_name.strip(), phone=phone, email=body.parent.email, city=body.parent.city
        )
        db.add(parent)
        await db.flush()
    else:
        raise crm_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "parent_required")

    student = None
    if body.student and body.student.model_dump(exclude_unset=True):
        student = CrmStudent(parent_id=parent.id)
        _apply_student(student, body.student)
        db.add(student)
        await db.flush()

    # A manager's own lead goes straight to qualification; one entered by the
    # owner or the head of sales waits in the inbox for someone to take it.
    mine = user.role == UserRole.sales_manager
    deal = CrmDeal(
        parent_id=parent.id,
        student_id=student.id if student else None,
        stage=DealStage.qualification if mine else DealStage.unsorted,
        manager_id=user.id if mine else None,
        source=body.source,
        first_message=body.first_message,
    )
    db.add(deal)
    await db.flush()
    _event(db, deal, user, "created", {"stage": deal.stage.value})
    await db.commit()
    return deal


async def accept(db: AsyncSession, user: User, deal_id: uuid.UUID) -> CrmDeal:
    deal = await get_deal(db, user, deal_id, for_update=True)
    if deal.stage != DealStage.unsorted or deal.manager_id is not None:
        raise crm_error(status.HTTP_409_CONFLICT, "deal_already_accepted")
    deal.manager_id = user.id
    deal.stage = DealStage.qualification
    _event(db, deal, user, "accepted")
    await db.commit()
    return deal


# ── edit ────────────────────────────────────────────────────────────────────


async def patch_deal(db: AsyncSession, user: User, deal_id: uuid.UUID, body: schemas.DealPatch) -> CrmDeal:
    deal = await get_deal(db, user, deal_id, for_update=True)
    _require_owned(user, deal)
    _require_open(deal)
    sent = body.model_dump(exclude_unset=True)

    if body.parent is not None:
        parent = await db.get(CrmParent, deal.parent_id)
        data = body.parent.model_dump(exclude_unset=True)
        if "phone" in data:
            data["phone"] = normalize_phone(data["phone"])
        for field, value in data.items():
            setattr(parent, field, value)
    if body.student is not None:
        student = await db.get(CrmStudent, deal.student_id) if deal.student_id else None
        if student is None:
            student = CrmStudent(parent_id=deal.parent_id)
            db.add(student)
            await db.flush()
            deal.student_id = student.id
        _apply_student(student, body.student)

    if "is_target" in sent:
        if body.is_target is False and STAGE_ORDER.index(deal.stage) > _QUALIFICATION_INDEX:
            raise crm_error(status.HTTP_409_CONFLICT, "deal_non_target_advanced")
        deal.is_target = body.is_target
        deal.non_target_reason = body.non_target_reason if body.is_target is False else None
        _event(db, deal, user, "qualified", {"is_target": body.is_target, "reason": deal.non_target_reason})

    if "tariff_code" in sent and body.tariff_code != deal.tariff_code:
        if deal.paid_at is not None and not _supervisor(user):
            raise crm_error(status.HTTP_409_CONFLICT, "deal_paid_locked")
        tariff = await db.get(CrmTariff, body.tariff_code) if body.tariff_code else None
        if body.tariff_code and (tariff is None or not tariff.active):
            raise crm_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "tariff_not_found")
        deal.tariff_code = body.tariff_code
        # The price is fixed on the day the tariff is chosen (ТЗ §3.7), and
        # so is whether a psychologist reviews the report.
        deal.price = tariff.price if tariff else None
        deal.psychologist_review = tariff.psychologist_review if tariff else None
        _event(db, deal, user, "tariff", {"tariff": deal.tariff_code, "price": deal.price})

    if "discount" in sent and body.discount is not None and body.discount != deal.discount:
        if deal.paid_at is not None and not _supervisor(user):
            raise crm_error(status.HTTP_409_CONFLICT, "deal_paid_locked")
        audit.record(
            db, actor=user, action="crm.discount_changed", entity_type="crm_deal", entity_id=deal.id,
            before={"discount": deal.discount}, after={"discount": body.discount},
        )
        _event(db, deal, user, "discount", {"from": deal.discount, "to": body.discount})
        deal.discount = body.discount

    if "manager_id" in sent and body.manager_id != deal.manager_id:
        if not _supervisor(user):
            raise crm_error(status.HTTP_403_FORBIDDEN, "deal_reassign_forbidden")
        manager = await db.get(User, body.manager_id) if body.manager_id else None
        if body.manager_id and (manager is None or manager.role not in (UserRole.sales_manager, UserRole.sales_head)):
            raise crm_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "manager_not_found")
        audit.record(
            db, actor=user, action="crm.manager_changed", entity_type="crm_deal", entity_id=deal.id,
            before={"manager_id": str(deal.manager_id) if deal.manager_id else None},
            after={"manager_id": str(body.manager_id) if body.manager_id else None},
        )
        deal.manager_id = body.manager_id
        _event(db, deal, user, "manager", {"manager_id": str(body.manager_id) if body.manager_id else None})

    if "source" in sent:
        deal.source = body.source
    await db.commit()
    return deal


def _check_move(user: User, deal: CrmDeal, target: DealStage) -> None:
    """The rules of ТЗ §3.3 that hold while every stage moves by hand."""
    index = STAGE_ORDER.index(target)
    paid = deal.paid_at is not None
    if target == DealStage.unsorted:
        raise crm_error(status.HTTP_409_CONFLICT, "stage_unsorted")
    if target == DealStage.paid and not paid:
        raise crm_error(status.HTTP_409_CONFLICT, "stage_paid_via_payment")
    if index > _PAID_INDEX:
        # After-sale stages: the platform will move them by events; until
        # then only the head of sales or the owner does.
        if not _supervisor(user):
            raise crm_error(status.HTTP_403_FORBIDDEN, "stage_after_sale_forbidden")
        if not paid:
            raise crm_error(status.HTTP_409_CONFLICT, "deal_not_paid")
    if paid and index < _PAID_INDEX:
        raise crm_error(status.HTTP_409_CONFLICT, "deal_paid_stage_back")
    if index > _QUALIFICATION_INDEX and deal.is_target is False:
        raise crm_error(status.HTTP_409_CONFLICT, "deal_non_target")
    if index >= _CONSULTATION_INDEX and deal.is_target is not True:
        raise crm_error(status.HTTP_409_CONFLICT, "deal_target_required")
    if index >= _INVOICE_INDEX and not deal.tariff_code:
        raise crm_error(status.HTTP_409_CONFLICT, "deal_tariff_required")


async def move(db: AsyncSession, user: User, deal_id: uuid.UUID, target: DealStage) -> CrmDeal:
    deal = await get_deal(db, user, deal_id, for_update=True)
    _require_owned(user, deal)
    _require_open(deal)
    if deal.stage == target:
        return deal
    _check_move(user, deal, target)
    audit.record(
        db, actor=user, action="crm.stage_changed", entity_type="crm_deal", entity_id=deal.id,
        before={"stage": deal.stage.value}, after={"stage": target.value},
    )
    _event(db, deal, user, "stage", {"from": deal.stage.value, "to": target.value})
    deal.stage = target
    await db.commit()
    return deal


# ── payment, consent, closing, notes ────────────────────────────────────────


async def mark_payment(db: AsyncSession, user: User, deal_id: uuid.UUID, body: schemas.PaymentIn) -> CrmDeal:
    deal = await get_deal(db, user, deal_id, for_update=True)
    _require_owned(user, deal)
    _require_open(deal)
    if deal.paid_at is not None and not _supervisor(user):
        # Changing a recorded payment is for the head of sales and the owner (ТЗ §3.7).
        raise crm_error(status.HTTP_403_FORBIDDEN, "payment_change_forbidden")
    if deal.is_target is not True:
        raise crm_error(status.HTTP_409_CONFLICT, "deal_target_required")
    if not deal.tariff_code:
        raise crm_error(status.HTTP_409_CONFLICT, "deal_tariff_required")
    before = {"amount": deal.paid_amount, "method": deal.payment_method.value if deal.payment_method else None}
    deal.paid_amount = body.amount
    deal.payment_method = body.method
    deal.paid_at = body.paid_at or tz.now_utc()
    if STAGE_ORDER.index(deal.stage) < _PAID_INDEX:
        _event(db, deal, user, "stage", {"from": deal.stage.value, "to": DealStage.paid.value})
        deal.stage = DealStage.paid
    audit.record(
        db, actor=user, action="crm.payment_marked", entity_type="crm_deal", entity_id=deal.id,
        before=before, after={"amount": body.amount, "method": body.method.value},
    )
    _event(db, deal, user, "payment", {"amount": body.amount, "method": body.method.value})
    await db.commit()
    return deal


async def cancel_payment(db: AsyncSession, user: User, deal_id: uuid.UUID) -> CrmDeal:
    deal = await get_deal(db, user, deal_id, for_update=True)
    if not _supervisor(user):
        raise crm_error(status.HTTP_403_FORBIDDEN, "payment_change_forbidden")
    _require_open(deal)
    if deal.paid_at is None:
        raise crm_error(status.HTTP_409_CONFLICT, "deal_not_paid")
    if (await _active_meetings(db, [deal.id])).get(deal.id) or deal.stage != DealStage.paid:
        raise crm_error(status.HTTP_409_CONFLICT, "payment_cancel_blocked")
    audit.record(
        db, actor=user, action="crm.payment_cancelled", entity_type="crm_deal", entity_id=deal.id,
        before={"amount": deal.paid_amount}, after=None,
    )
    deal.paid_amount = deal.paid_at = deal.payment_method = None
    deal.stage = DealStage.invoice
    _event(db, deal, user, "payment_cancelled")
    await db.commit()
    return deal


async def set_consent(db: AsyncSession, user: User, deal_id: uuid.UUID, given: bool) -> CrmDeal:
    deal = await get_deal(db, user, deal_id)
    _require_owned(user, deal)
    parent = await db.get(CrmParent, deal.parent_id)
    audit.record(
        db, actor=user, action="crm.consent_changed", entity_type="crm_parent", entity_id=parent.id,
        before={"consent": parent.consent}, after={"consent": given},
    )
    parent.consent = given
    parent.consent_at = tz.now_utc()
    _event(db, deal, user, "consent", {"given": given})
    await db.commit()
    return deal


async def close(db: AsyncSession, user: User, deal_id: uuid.UUID, body: schemas.CloseIn) -> CrmDeal:
    deal = await get_deal(db, user, deal_id, for_update=True)
    _require_owned(user, deal)
    if deal.result != DealResult.open:
        raise crm_error(status.HTTP_409_CONFLICT, "deal_closed")
    if body.result == "won":
        # Success is the published report (ТЗ §3.3.1); until the platform
        # sends it, only the head of sales or the owner records it.
        if not _supervisor(user):
            raise crm_error(status.HTTP_403_FORBIDDEN, "deal_win_forbidden")
        if deal.paid_at is None:
            raise crm_error(status.HTTP_409_CONFLICT, "deal_not_paid")
        deal.result = DealResult.won
    else:
        if body.reason is None:
            raise crm_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "close_reason_required")
        if deal.paid_at is not None and not _supervisor(user):
            raise crm_error(status.HTTP_403_FORBIDDEN, "deal_close_paid_forbidden")
        deal.result = DealResult.lost
        deal.lost_reason = body.reason
    deal.close_comment = body.comment
    deal.closed_at = tz.now_utc()
    audit.record(
        db, actor=user, action="crm.deal_closed", entity_type="crm_deal", entity_id=deal.id,
        before={"result": "open"},
        after={"result": deal.result.value, "reason": deal.lost_reason.value if deal.lost_reason else None},
        reason=body.comment,
    )
    _event(
        db, deal, user, "closed",
        {"result": deal.result.value, "reason": deal.lost_reason.value if deal.lost_reason else None},
        body.comment,
    )
    await db.commit()
    return deal


async def add_note(db: AsyncSession, user: User, deal_id: uuid.UUID, text: str) -> CrmDeal:
    deal = await get_deal(db, user, deal_id)
    _require_owned(user, deal)
    _event(db, deal, user, "note", text=text.strip())
    await db.commit()
    return deal


# ── booking ─────────────────────────────────────────────────────────────────


async def _previous_specialist(db: AsyncSession, deal: CrmDeal) -> uuid.UUID | None:
    """The specialist who already worked with this family: a returning client
    stays with them when they are free at the chosen time — the manager still
    sees no names. The same child's deal first (by Profile account, then by
    the CRM student), then the family's latest one."""
    rows = (
        await db.execute(
            select(CrmDeal.specialist_id, CrmDeal.student_user_id, CrmDeal.student_id)
            .where(CrmDeal.parent_id == deal.parent_id, CrmDeal.id != deal.id, CrmDeal.specialist_id.is_not(None))
            .order_by(CrmDeal.created_at.desc())
        )
    ).all()
    if not rows:
        return None

    def rank(row) -> tuple[bool, bool]:
        same_account = deal.student_user_id is not None and row.student_user_id == deal.student_user_id
        same_student = deal.student_id is not None and row.student_id == deal.student_id
        return (not same_account, not same_student)

    # sorted() is stable: within a rank the latest deal stays first.
    return sorted(rows, key=rank)[0].specialist_id


async def book(db: AsyncSession, user: User, deal_id: uuid.UUID, body: schemas.BookingIn) -> CrmDeal:
    """Book the call the tariff calls for (ТЗ §3.9): «Тестирование» and «Пакет»
    get the 30-minute intro, «Консультация» its 60-minute call."""
    deal = await get_deal(db, user, deal_id, for_update=True)
    _require_owned(user, deal)
    _require_open(deal)
    parent = await db.get(CrmParent, deal.parent_id)
    if deal.paid_at is None:
        raise crm_error(status.HTTP_409_CONFLICT, "deal_not_paid")
    if deal.is_target is not True:
        raise crm_error(status.HTTP_409_CONFLICT, "deal_target_required")
    if parent.consent is not True:
        raise crm_error(status.HTTP_409_CONFLICT, "consent_required")
    if (await _active_meetings(db, [deal.id])).get(deal.id):
        raise crm_error(status.HTTP_409_CONFLICT, "deal_already_booked")
    # Sold without a specialist (no review, no call): nothing to book.
    if deal.psychologist_review is False:
        raise crm_error(status.HTTP_409_CONFLICT, "deal_no_meeting")
    tariff = await db.get(CrmTariff, deal.tariff_code)

    handoff = body.handoff.model_dump()
    handoff["tariff"] = tariff.name
    handoff["consent_at"] = parent.consent_at.isoformat() if parent.consent_at else None
    meeting = await booking.book(
        db, actor=user, start=body.start, minutes=FIRST_CALL_MINUTES, deal_id=deal.id, handoff=handoff,
        prefer=await _previous_specialist(db, deal),
    )

    # The handoff card also fills the CRM student.
    student = await db.get(CrmStudent, deal.student_id) if deal.student_id else None
    if student is None:
        student = CrmStudent(parent_id=deal.parent_id)
        db.add(student)
        await db.flush()
        deal.student_id = student.id
    h = body.handoff
    student.full_name, student.age, student.gender, student.grade = h.student_name, h.age, h.gender, h.grade
    student.study_language, student.russian_level = h.study_language, h.russian_level

    deal.specialist_id = meeting.specialist_id
    await progress.assign_specialist(db, deal)
    audit.record(
        db, actor=user, action="crm.meeting_booked", entity_type="crm_deal", entity_id=deal.id,
        after={"meeting_id": str(meeting.id), "start": meeting.start_at.isoformat(), "type": meeting.type.value},
    )
    _event(db, deal, user, "booked", {"start": meeting.start_at.isoformat(), "type": meeting.type.value})
    await db.commit()
    return deal


# ── clients ─────────────────────────────────────────────────────────────────


async def clients(db: AsyncSession, user: User, q: str | None = None) -> list[schemas.ClientRow]:
    """Parents with their children, deals and calls (ТЗ §3.2). A sales manager
    sees the clients of their own deals and of the inbox."""
    query = select(CrmParent).order_by(CrmParent.created_at.desc())
    if (clause := _visible_clause(user)) is not None:
        query = query.where(CrmParent.id.in_(select(CrmDeal.parent_id).where(clause)))
    if q and (text := q.strip()):
        conditions = [CrmParent.full_name.ilike(f"%{text}%")]
        digits = re.sub(r"\D", "", text)
        if len(digits) >= 4:
            conditions.append(CrmParent.phone.like(f"%{digits[-10:]}%"))
        query = query.where(or_(*conditions))
    parents = list((await db.execute(query.limit(500))).scalars())
    ids = [p.id for p in parents]
    if not ids:
        return []
    students: dict[uuid.UUID, list[str]] = {}
    for parent_id, name in (await db.execute(select(CrmStudent.parent_id, CrmStudent.full_name).where(
        CrmStudent.parent_id.in_(ids), CrmStudent.full_name.is_not(None)
    ))).all():
        students.setdefault(parent_id, []).append(name)
    deals_by_parent: dict[uuid.UUID, list[CrmDeal]] = {}
    for deal in (await db.execute(select(CrmDeal).where(CrmDeal.parent_id.in_(ids)))).scalars():
        deals_by_parent.setdefault(deal.parent_id, []).append(deal)
    meeting_rows = (await db.execute(
        select(CrmDeal.parent_id, Meeting.status)
        .join(Meeting, Meeting.deal_id == CrmDeal.id)
        .where(CrmDeal.parent_id.in_(ids), Meeting.status != MeetingStatus.cancelled)
    )).all()
    out = []
    for parent in parents:
        own = deals_by_parent.get(parent.id, [])
        statuses = [st for pid, st in meeting_rows if pid == parent.id]
        open_deal = next((d for d in own if d.result == DealResult.open), None)
        out.append(schemas.ClientRow(
            id=parent.id,
            full_name=parent.full_name,
            phone=parent.phone,
            city=parent.city,
            students=sorted(set(students.get(parent.id, []))),
            deals=len(own),
            open_deal_id=open_deal.id if open_deal else (own[0].id if own else None),
            meetings_done=sum(st == MeetingStatus.done for st in statuses),
            meetings_total=len(statuses),
            no_shows=sum(st == MeetingStatus.no_show for st in statuses),
            paid_total=sum(d.paid_amount or 0 for d in own),
        ))
    return out
