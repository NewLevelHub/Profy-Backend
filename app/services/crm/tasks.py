"""Tasks of the sales team (ТЗ §3.11, PRO-526).

A sales manager sees and sets tasks only for themself; the owner and the head
of sales see everyone's and set them for anyone in sales. Reminders and the
digital funnel's automatic tasks come later — for now tasks are set by hand,
plus the owner's task when a manager asks to move a call.
"""

import uuid
from datetime import timedelta
from typing import Literal

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import CrmDeal, CrmDealEvent, CrmParent, CrmStudent, CrmTask, TaskType
from app.models.scheduling import Meeting
from app.models.user import User, UserRole
from app.schemas import crm as schemas
from app.services import tz
from app.services.crm.meetings import OPEN
from app.services.crm.deals import SUPERVISORS, _require_owned, _user_ref, _users, crm_error, get_deal

# How long the owner has to answer a request to move a call.
REQUEST_DUE = timedelta(hours=2)

# Who can be given a task.
ASSIGNEE_ROLES = (UserRole.owner, UserRole.sales_head, UserRole.sales_manager)


def _supervisor(user: User) -> bool:
    return user.role in SUPERVISORS


async def sales_users(db: AsyncSession) -> list[schemas.SalesUser]:
    rows = await db.execute(
        select(User)
        .where(User.role.in_(ASSIGNEE_ROLES), User.is_active.is_(True))
        .order_by(User.full_name, User.email)
    )
    return [schemas.SalesUser(id=u.id, name=u.full_name or u.email, role=u.role.value) for u in rows.scalars()]


async def _assignee(db: AsyncSession, actor: User, assignee_id: uuid.UUID | None) -> User:
    if assignee_id is None or assignee_id == actor.id:
        return actor
    if not _supervisor(actor):
        raise crm_error(status.HTTP_403_FORBIDDEN, "task_assign_forbidden")
    assignee = await db.get(User, assignee_id)
    if assignee is None or assignee.role not in ASSIGNEE_ROLES or not assignee.is_active:
        raise crm_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "assignee_not_found")
    return assignee


def _event(db: AsyncSession, deal_id: uuid.UUID | None, actor: User, kind: str, data: dict, text: str | None) -> None:
    if deal_id:
        db.add(CrmDealEvent(deal_id=deal_id, actor_id=actor.id, kind=kind, data=data, text=text))


async def get_task(db: AsyncSession, user: User, task_id: uuid.UUID) -> CrmTask:
    task = await db.get(CrmTask, task_id, with_for_update=True)
    if task is None or (not _supervisor(user) and task.assignee_id != user.id):
        raise crm_error(status.HTTP_404_NOT_FOUND, "task_not_found")
    return task


async def task_out(db: AsyncSession, tasks: list[CrmTask]) -> list[schemas.TaskOut]:
    users = await _users(db, {t.assignee_id for t in tasks} | {t.created_by for t in tasks})
    deal_ids = {t.deal_id for t in tasks if t.deal_id}
    titles: dict[uuid.UUID, str] = {}
    if deal_ids:
        rows = await db.execute(
            select(CrmDeal.id, CrmParent.full_name, CrmStudent.full_name)
            .join(CrmParent, CrmParent.id == CrmDeal.parent_id)
            .outerjoin(CrmStudent, CrmStudent.id == CrmDeal.student_id)
            .where(CrmDeal.id.in_(deal_ids))
        )
        titles = {deal_id: " · ".join(n for n in (parent, student) if n) for deal_id, parent, student in rows.all()}
    return [
        schemas.TaskOut(
            id=t.id,
            deal_id=t.deal_id,
            deal_title=titles.get(t.deal_id) if t.deal_id else None,
            type=t.type,
            text=t.text,
            due_at=t.due_at,
            done_at=t.done_at,
            result=t.result,
            assignee=_user_ref(users.get(t.assignee_id)),
            created_by=_user_ref(users.get(t.created_by)),
            created_at=t.created_at,
        )
        for t in tasks
    ]


async def list_tasks(
    db: AsyncSession,
    user: User,
    *,
    scope: Literal["mine", "all"] = "mine",
    state: Literal["open", "done"] = "open",
    deal_id: uuid.UUID | None = None,
    assignee_id: uuid.UUID | None = None,
) -> list[schemas.TaskOut]:
    query = select(CrmTask)
    if not _supervisor(user) or scope == "mine":
        query = query.where(CrmTask.assignee_id == user.id)
    elif assignee_id:
        query = query.where(CrmTask.assignee_id == assignee_id)
    if deal_id:
        query = query.where(CrmTask.deal_id == deal_id)
    if state == "open":
        query = query.where(CrmTask.done_at.is_(None)).order_by(CrmTask.due_at)
    else:
        query = query.where(CrmTask.done_at.is_not(None)).order_by(CrmTask.done_at.desc()).limit(200)
    return await task_out(db, list((await db.execute(query)).scalars()))


async def deal_tasks(db: AsyncSession, deal_id: uuid.UUID) -> list[schemas.TaskOut]:
    """Every task of the deal for its card: open first by due time, then done."""
    rows = await db.execute(
        select(CrmTask)
        .where(CrmTask.deal_id == deal_id)
        .order_by(CrmTask.done_at.is_not(None), CrmTask.due_at)
    )
    return await task_out(db, list(rows.scalars()))


async def create_task(db: AsyncSession, user: User, body: schemas.TaskCreate) -> CrmTask:
    if body.deal_id:
        deal = await get_deal(db, user, body.deal_id)
        _require_owned(user, deal)
    assignee = await _assignee(db, user, body.assignee_id)
    task = CrmTask(
        deal_id=body.deal_id,
        assignee_id=assignee.id,
        created_by=user.id,
        type=body.type,
        text=body.text.strip(),
        due_at=body.due_at,
    )
    db.add(task)
    await db.flush()
    _event(db, body.deal_id, user, "task", {"task_id": str(task.id), "due_at": task.due_at.isoformat(),
                                            "type": task.type.value}, task.text)
    await db.commit()
    return task


async def patch_task(db: AsyncSession, user: User, task_id: uuid.UUID, body: schemas.TaskPatch) -> CrmTask:
    task = await get_task(db, user, task_id)
    if task.done_at is not None:
        raise crm_error(status.HTTP_409_CONFLICT, "task_already_done")
    sent = body.model_dump(exclude_unset=True)
    if sent.get("text"):
        task.text = body.text.strip()
    if sent.get("due_at"):
        task.due_at = body.due_at
    if "assignee_id" in sent:
        task.assignee_id = (await _assignee(db, user, body.assignee_id)).id
    await db.commit()
    return task


async def complete_task(db: AsyncSession, user: User, task_id: uuid.UUID, result: str | None) -> CrmTask:
    task = await get_task(db, user, task_id)
    if task.done_at is not None:
        raise crm_error(status.HTTP_409_CONFLICT, "task_already_done")
    task.done_at = tz.now_utc()
    task.result = result.strip() if result and result.strip() else None
    _event(db, task.deal_id, user, "task_done", {"task_id": str(task.id), "type": task.type.value}, task.result)
    await db.commit()
    return task


async def request_reschedule(db: AsyncSession, user: User, meeting: Meeting, comment: str) -> CrmTask:
    """A manager asks to move a call (ТЗ §4.5): the owner gets a task with the
    client's request and moves the call from the visit window in one go."""
    if meeting.status not in OPEN:
        raise crm_error(status.HTTP_409_CONFLICT, "meeting_status_invalid")
    if tz.now_utc() >= meeting.start_at:
        raise crm_error(status.HTTP_409_CONFLICT, "meeting_started")
    owner = await db.scalar(
        select(User).where(User.role == UserRole.owner, User.is_active.is_(True)).order_by(User.created_at).limit(1)
    )
    if owner is None:
        raise crm_error(status.HTTP_409_CONFLICT, "owner_not_found")
    task = CrmTask(
        deal_id=meeting.deal_id,
        assignee_id=owner.id,
        created_by=user.id,
        type=TaskType.reschedule,
        text=comment.strip(),
        # Two hours to answer, but never later than the call itself.
        due_at=min(tz.now_utc() + REQUEST_DUE, meeting.start_at),
    )
    db.add(task)
    await db.flush()
    _event(db, meeting.deal_id, user, "reschedule_requested",
           {"task_id": str(task.id), "meeting_id": str(meeting.id), "start": meeting.start_at.isoformat()}, task.text)
    await db.commit()
    return task
