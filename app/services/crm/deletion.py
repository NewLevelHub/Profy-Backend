"""«Удалить сделку» for the owner and the admin (a mistaken or test deal).

Unlike closing, it leaves nothing behind but the journal entry: the deal's
calls give their time back, and a client with no other deal goes as well, so
the next message from that phone is a new lead. A student's Profile account is
a separate thing and stays, and goes back to the specialist of their deal left,
if any.
"""

import uuid

from fastapi import status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import CrmDeal, CrmMessage, CrmParent, CrmStudent
from app.models.scheduling import Meeting, SlotState, SpecialistSlot
from app.models.user import User
from app.services import audit, tz
from app.services.crm import progress
from app.services.crm.errors import crm_error


async def delete_deal(db: AsyncSession, actor: User, deal_id: uuid.UUID) -> None:
    deal = await db.get(CrmDeal, deal_id, with_for_update=True)
    if deal is None:
        raise crm_error(status.HTTP_404_NOT_FOUND, "deal_not_found")
    parent = await db.get(CrmParent, deal.parent_id)
    meeting_ids = list(await db.scalars(select(Meeting.id).where(Meeting.deal_id == deal.id)))
    audit.record(
        db, actor=actor, action="deal.deleted", entity_type="deal", entity_id=deal.id,
        before={
            "client": parent.full_name, "stage": deal.stage.value, "result": deal.result.value,
            "tariff": deal.tariff_code, "price": deal.price, "paid_amount": deal.paid_amount,
            "meetings": len(meeting_ids),
        },
    )
    if meeting_ids:
        await db.execute(
            update(SpecialistSlot)
            .where(SpecialistSlot.meeting_id.in_(meeting_ids))
            .values(state=SlotState.free, meeting_id=None, updated_by=actor.id, updated_at=tz.now_utc())
        )
        await db.execute(delete(Meeting).where(Meeting.id.in_(meeting_ids)))
    await db.execute(delete(CrmMessage).where(CrmMessage.deal_id == deal.id))

    student_id, parent_id = deal.student_id, deal.parent_id
    account_id, specialist_id = deal.student_user_id, deal.specialist_id
    await db.delete(deal)
    await db.flush()
    if account_id:
        if specialist_id:
            await progress.release_student(db, account_id, specialist_id)
        await progress.settle_student(db, account_id)
    if not await db.scalar(select(func.count()).select_from(CrmDeal).where(CrmDeal.parent_id == parent_id)):
        await db.delete(parent)  # with its students and the rest of its messages
    elif student_id and not await db.scalar(
        select(func.count()).select_from(CrmDeal).where(CrmDeal.student_id == student_id)
    ):
        await db.execute(delete(CrmStudent).where(CrmStudent.id == student_id))
    await db.commit()
