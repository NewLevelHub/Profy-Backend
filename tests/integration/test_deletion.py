"""«Удалить»: deals and accounts, for the owner and the platform admin."""

from datetime import time, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact import Artifact, ArtifactType
from app.models.audit_log import AuditLog
from app.models.crm import (
    CrmDeal,
    CrmMessage,
    CrmParent,
    CrmStudent,
    CrmTask,
    DealResult,
    MessageDirection,
    MessageStatus,
    TaskType,
)
from app.models.profile import AgeGroup, Profile
from app.models.psychologist_assignment import PsychologistStudentAssignment
from app.models.scheduling import Meeting, SlotState, SpecialistSlot
from app.models.user import User, UserRole
from app.services import tz
from app.services.crm import progress
from tests.integration.test_crm_deals import (  # noqa: F401 — fixtures
    URL,
    _booked_with,
    _create,
    _h,
    _holders,
    _link,
    _user,
    manager,
)
from tests.integration.test_crm_meetings_tasks import _booked

ADMIN_URL = "/api/v1/admin"


# ── deals ───────────────────────────────────────────────────────────────────


async def test_only_owner_and_admin_delete_a_deal(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User, admin_user: User
) -> None:
    head = await _user(db_session, UserRole.sales_head)
    owner = await _user(db_session, UserRole.owner)
    first = await _create(client, manager)
    second = await _create(client, manager)

    for user in (manager, head):
        denied = await client.delete(f"{URL}/deals/{first['id']}", headers=_h(user))
        assert denied.status_code == 403
    assert (await client.delete(f"{URL}/deals/{first['id']}", headers=_h(owner))).status_code == 204
    assert (await client.delete(f"{URL}/deals/{second['id']}", headers=_h(admin_user))).status_code == 204
    assert (await client.delete(f"{URL}/deals/{second['id']}", headers=_h(owner))).status_code == 404
    assert (await client.get(f"{URL}/deals/{second['id']}", headers=_h(owner))).status_code == 404


async def test_admin_reads_the_deals_but_does_not_change_them(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User, admin_user: User
) -> None:
    deal = await _create(client, manager)
    path = f"{URL}/deals/{deal['id']}"
    assert (await client.get(f"{URL}/meta", headers=_h(admin_user))).status_code == 200
    board = (await client.get(f"{URL}/deals", headers=_h(admin_user))).json()
    card = next(d for d in board if d["id"] == deal["id"])
    assert card["parent_name"] == "Асель Нурланова"
    assert (await client.get(path, headers=_h(admin_user))).status_code == 200
    assert (await client.patch(path, json={"is_target": True}, headers=_h(admin_user))).status_code == 403


async def test_deleting_a_deal_frees_its_calls_and_removes_the_client(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    owner = await _user(db_session, UserRole.owner)
    specialist = await _user(db_session, UserRole.psychologist)
    specialist_id = specialist.id
    deal, meeting = await _booked(client, db_session, manager, specialist)
    deal_row = await db_session.get(CrmDeal, deal["id"])
    parent_id, student_id = deal_row.parent_id, deal_row.student_id
    db_session.add(
        CrmMessage(
            parent_id=parent_id, deal_id=deal_row.id, phone="+77010000000", direction=MessageDirection.incoming,
            text="Здравствуйте", status=MessageStatus.received, at=tz.now_utc(),
        )
    )
    await db_session.flush()

    assert (await client.delete(f"{URL}/deals/{deal['id']}", headers=_h(owner))).status_code == 204

    db_session.expire_all()
    assert await db_session.get(Meeting, meeting["id"]) is None
    slot = await db_session.scalar(select(SpecialistSlot).where(SpecialistSlot.specialist_id == specialist_id))
    assert slot.state == SlotState.free and slot.meeting_id is None
    assert await db_session.get(CrmParent, parent_id) is None
    assert await db_session.get(CrmStudent, student_id) is None
    assert not list(await db_session.scalars(select(CrmMessage).where(CrmMessage.parent_id == parent_id)))
    entry = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == deal["id"], AuditLog.action == "deal.deleted"))
    assert entry.actor_role == "owner" and entry.before["client"] == "Асель Нурланова"


async def test_a_client_with_another_deal_stays(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    owner = await _user(db_session, UserRole.owner)
    first = await _create(client, manager)
    row = await db_session.get(CrmDeal, first["id"])
    other = CrmDeal(parent_id=row.parent_id, student_id=row.student_id, stage=row.stage)
    db_session.add(other)
    await db_session.flush()
    parent_id, student_id, other_id = row.parent_id, row.student_id, other.id

    assert (await client.delete(f"{URL}/deals/{first['id']}", headers=_h(owner))).status_code == 204

    db_session.expire_all()
    assert await db_session.get(CrmParent, parent_id) is not None
    assert await db_session.get(CrmStudent, student_id) is not None
    assert await db_session.get(CrmDeal, other_id) is not None


# ── accounts ────────────────────────────────────────────────────────────────


async def test_owner_and_admin_delete_a_student_with_their_data(
    client: httpx.AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    owner = await _user(db_session, UserRole.owner)
    actors = [(owner.id, _h(owner)), (admin_user.id, _h(admin_user))]
    for actor_id, headers in actors:
        student = await _user(db_session, UserRole.student)
        profile = Profile(user_id=student.id, name="Камила", age=15, grade=9, city="Алматы", country="Казахстан", language="ru", age_group=AgeGroup.senior)
        db_session.add(profile)
        await db_session.flush()
        db_session.add(Artifact(profile_id=profile.id, type=ArtifactType.hobby, value="шахматы"))
        await db_session.flush()
        student_id, profile_id = student.id, profile.id

        response = await client.delete(f"{ADMIN_URL}/users/{student_id}", headers=headers)
        assert response.status_code == 204, response.text

        db_session.expire_all()
        assert await db_session.get(User, student_id) is None
        assert await db_session.get(Profile, profile_id) is None
        entry = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(student_id)))
        assert entry.action == "user.deleted" and entry.actor_id == actor_id
        assert (await client.delete(f"{ADMIN_URL}/users/{student_id}", headers=headers)).status_code == 404


async def test_others_cannot_delete_accounts(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User, test_user: User
) -> None:
    head = await _user(db_session, UserRole.sales_head)
    target = await _user(db_session, UserRole.student)
    for actor in (manager, head, test_user):
        assert (await client.delete(f"{ADMIN_URL}/users/{target.id}", headers=_h(actor))).status_code == 403
        assert (await client.get(f"{ADMIN_URL}/users", headers=_h(actor))).status_code == 403


async def test_owners_admins_and_oneself_are_locked(
    client: httpx.AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    owner = await _user(db_session, UserRole.owner)
    other_owner = await _user(db_session, UserRole.owner)
    other_admin = await _user(db_session, UserRole.admin)
    for actor, target in ((owner, owner), (owner, other_owner), (owner, other_admin), (admin_user, admin_user), (admin_user, owner)):
        response = await client.delete(f"{ADMIN_URL}/users/{target.id}", headers=_h(actor))
        assert response.status_code == 403
        assert response.json()["error_code"] == "user_delete_locked"


async def test_owner_lists_students(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    owner = await _user(db_session, UserRole.owner)
    student = await _user(db_session, UserRole.student)
    response = await client.get(f"{ADMIN_URL}/users", params={"search": student.email}, headers=_h(owner))
    assert response.status_code == 200
    assert [u["id"] for u in response.json()["items"]] == [str(student.id)]


async def test_a_manager_hands_over_open_deals_and_tasks_first(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    owner = await _user(db_session, UserRole.owner)
    manager_id, owner_h = manager.id, _h(owner)
    deal = await _create(client, manager)
    row = await db_session.get(CrmDeal, deal["id"])
    row.manager_id = manager_id
    await db_session.flush()

    refused = await client.delete(f"{ADMIN_URL}/users/{manager_id}", headers=owner_h)
    assert refused.status_code == 409
    assert refused.json()["error_code"] == "user_has_deals" and refused.json()["count"] == 1

    row.manager_id = owner.id
    task = CrmTask(
        deal_id=row.id, type=TaskType.call, text="Позвонить", due_at=tz.now_utc() + timedelta(days=1),
        assignee_id=manager_id, created_by=owner.id,
    )
    db_session.add(task)
    await db_session.flush()
    refused = await client.delete(f"{ADMIN_URL}/users/{manager_id}", headers=owner_h)
    assert refused.status_code == 409 and refused.json()["error_code"] == "user_has_tasks"

    task.done_at = tz.now_utc()
    await db_session.flush()
    assert (await client.delete(f"{ADMIN_URL}/users/{manager_id}", headers=owner_h)).status_code == 204


async def test_a_finished_deal_outlives_its_manager(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    owner = await _user(db_session, UserRole.owner)
    deal = await _create(client, manager)
    row = await db_session.get(CrmDeal, deal["id"])
    row.manager_id, row.result = manager.id, DealResult.won
    await db_session.flush()

    assert (await client.delete(f"{ADMIN_URL}/users/{manager.id}", headers=_h(owner))).status_code == 204

    db_session.expire_all()
    assert (await db_session.get(CrmDeal, deal["id"])).manager_id is None


async def test_a_specialist_who_held_a_call_on_an_open_deal_is_kept(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    """The deal went to someone else, but its first call goes with the account."""
    owner = await _user(db_session, UserRole.owner)
    specialist = await _user(db_session, UserRole.psychologist)
    other = await _user(db_session, UserRole.psychologist)
    _, meeting = await _booked(client, db_session, manager, specialist)
    row = await db_session.get(Meeting, meeting["id"])
    row.start_at = tz.now_utc() - timedelta(days=1)
    row.end_at = row.start_at + timedelta(minutes=30)
    (await db_session.get(CrmDeal, row.deal_id)).specialist_id = other.id
    await db_session.flush()

    held = await client.delete(f"{ADMIN_URL}/users/{specialist.id}", headers=_h(owner))
    assert held.status_code == 409 and held.json()["error_code"] == "user_has_deals"
    assert held.json()["count"] == 1


async def test_a_specialist_with_upcoming_calls_is_kept(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    owner = await _user(db_session, UserRole.owner)
    specialist = await _user(db_session, UserRole.psychologist)
    _, meeting = await _booked(client, db_session, manager, specialist)

    response = await client.delete(f"{ADMIN_URL}/users/{specialist.id}", headers=_h(owner))
    assert response.status_code == 409
    assert response.json()["error_code"] == "user_has_meetings"
    assert response.json()["count"] == 1

    # Past calls do not hold the account, the open deal still does: a student
    # without a psychologist cannot take the test.
    row = await db_session.get(Meeting, meeting["id"])
    row.start_at = tz.now_utc() - timedelta(days=1)
    row.end_at = row.start_at + timedelta(minutes=30)
    await db_session.flush()
    held = await client.delete(f"{ADMIN_URL}/users/{specialist.id}", headers=_h(owner))
    assert held.status_code == 409 and held.json()["error_code"] == "user_has_deals"

    (await db_session.get(CrmDeal, row.deal_id)).result = DealResult.won
    await db_session.flush()
    assert (await client.delete(f"{ADMIN_URL}/users/{specialist.id}", headers=_h(owner))).status_code == 204


async def test_a_won_deal_without_calls_does_not_lock_the_test(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    owner = await _user(db_session, UserRole.owner)
    specialist = await _user(db_session, UserRole.psychologist)
    student = await _user(db_session, UserRole.student)
    student_id = student.id
    deal, meeting = await _booked(client, db_session, manager, specialist)
    row = await db_session.get(CrmDeal, deal["id"])
    row.student_user_id, row.result = student_id, DealResult.won
    call = await db_session.get(Meeting, meeting["id"])
    call.start_at = tz.now_utc() - timedelta(days=1)
    call.end_at = call.start_at + timedelta(minutes=30)
    await db_session.flush()

    assert (await client.delete(f"{ADMIN_URL}/users/{specialist.id}", headers=_h(owner))).status_code == 204
    assert await progress.test_opens_at(db_session, student_id) == (True, None)


async def test_deleting_a_deal_returns_the_student_to_the_deal_left(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    owner = await _user(db_session, UserRole.owner)
    earlier = await _user(db_session, UserRole.psychologist, "Прежний")
    later = await _user(db_session, UserRole.psychologist, "Новый")
    student = await _user(db_session, UserRole.student)
    old, _ = await _booked_with(client, db_session, manager, earlier, time(9, 0))
    new, _ = await _booked_with(client, db_session, manager, later, time(10, 0))
    await _link(db_session, old, student, days_ago=9)
    await _link(db_session, new, student)
    db_session.add(PsychologistStudentAssignment(psychologist_id=later.id, student_id=student.id))
    await db_session.flush()

    assert (await client.delete(f"{URL}/deals/{new['id']}", headers=_h(owner))).status_code == 204
    assert await _holders(db_session, student) == ["Прежний"]

    # No deal left: nobody serves the student.
    assert (await client.delete(f"{URL}/deals/{old['id']}", headers=_h(owner))).status_code == 204
    assert await _holders(db_session, student) == []


async def test_deleting_a_deal_keeps_the_clients_chat_for_the_other_deal(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    owner = await _user(db_session, UserRole.owner)
    mistaken = await _create(client, manager)
    parent_id = mistaken["parent"]["id"]
    other = await client.post(f"{URL}/deals", json={"parent_id": parent_id}, headers=_h(manager))
    assert other.status_code == 201, other.text
    db_session.add(
        CrmMessage(
            parent_id=parent_id, deal_id=mistaken["id"], phone=mistaken["parent"]["phone"],
            direction=MessageDirection.incoming, text="Здравствуйте", status=MessageStatus.received, at=tz.now_utc(),
        )
    )
    await db_session.flush()

    assert (await client.delete(f"{URL}/deals/{mistaken['id']}", headers=_h(owner))).status_code == 204
    kept = await db_session.scalars(
        select(CrmMessage).where(CrmMessage.parent_id == parent_id).execution_options(populate_existing=True)
    )
    assert [message.text for message in kept] == ["Здравствуйте"]

