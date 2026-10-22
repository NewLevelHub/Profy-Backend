"""CRM calendar, the owner's visit window and tasks (docs/frontend-crm-api-contract.md)."""

import uuid
from datetime import time, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.scheduling import Meeting, MeetingStatus, MeetingType, SlotState, SpecialistSlot
from app.models.user import User, UserRole
from app.services import tz
from tests.integration.test_crm_deals import (
    FUTURE_DAY,
    URL,
    _create,
    _h,
    _handoff,
    _iso,
    _open_slots,
    _ready_to_book,
    _user,
    head,  # noqa: F401 — fixture
    manager,  # noqa: F401 — fixture
)


async def _booked(client: httpx.AsyncClient, db: AsyncSession, manager: User, specialist: User) -> tuple[dict, dict]:
    start = await _open_slots(db, specialist, FUTURE_DAY, time(10, 0), 1)
    deal = await _ready_to_book(client, manager)
    booked = await client.post(
        f"{URL}/deals/{deal['id']}/booking", json={"start": _iso(start), "handoff": _handoff()}, headers=_h(manager)
    )
    assert booked.status_code == 200, booked.text
    return booked.json(), booked.json()["meeting"]


# ── calendar ────────────────────────────────────────────────────────────────


async def test_calendar_names_only_for_supervisors(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User, head: User
) -> None:
    specialist = await _user(db_session, UserRole.psychologist, "Лолита")
    deal, meeting = await _booked(client, db_session, manager, specialist)
    params = {"from": FUTURE_DAY.isoformat(), "to": FUTURE_DAY.isoformat()}

    mine = (await client.get(f"{URL}/meetings", params=params, headers=_h(manager))).json()
    mine = [m for m in mine if m["id"] == meeting["id"]]
    assert len(mine) == 1
    assert mine[0]["specialist"] is None and mine[0]["student_name"] == "Камила Нурланова"

    assert mine[0]["mine"] is True and mine[0]["parent_name"] == "Асель Нурланова"

    # Another manager sees the time as «Занято» — no client, no deal.
    other = await _user(db_session, UserRole.sales_manager)
    busy = (await client.get(f"{URL}/meetings", params=params, headers=_h(other))).json()
    hidden = next(m for m in busy if m["id"] == meeting["id"])
    assert hidden["mine"] is False
    assert hidden["deal_id"] is None and hidden["student_name"] is None and hidden["parent_name"] is None
    assert (await client.get(f"{URL}/meetings/{meeting['id']}", headers=_h(other))).status_code == 404

    seen = (await client.get(f"{URL}/meetings", params=params, headers=_h(head))).json()
    assert seen[0]["specialist"]["name"] == "Лолита"


# ── statuses ────────────────────────────────────────────────────────────────


async def test_done_only_after_start_and_not_by_sales(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    specialist = await _user(db_session, UserRole.psychologist)
    owner = await _user(db_session, UserRole.owner)
    deal, meeting = await _booked(client, db_session, manager, specialist)
    path = f"{URL}/meetings/{meeting['id']}/status"

    early = await client.post(path, json={"status": "done"}, headers=_h(owner))
    assert early.json()["error_code"] == "meeting_not_started"
    by_manager = await client.post(path, json={"status": "no_show"}, headers=_h(manager))
    assert by_manager.status_code == 403

    confirmed = await client.post(path, json={"status": "confirmed"}, headers=_h(manager))
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "confirmed"
    assert confirmed.json()["history"][0]["action"] == "meeting.status_changed"


async def test_specialist_marks_own_past_call_in_profy(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    specialist = await _user(db_session, UserRole.psychologist)
    start = tz.now_utc().replace(second=0, microsecond=0) - timedelta(hours=2)
    meeting = Meeting(
        specialist_id=specialist.id, type=MeetingType.intro30, start_at=start, end_at=start + timedelta(minutes=30),
        handoff=_handoff(),
    )
    db_session.add(meeting)
    await db_session.flush()

    path = f"/api/v1/scheduling/specialists/me/meetings/{meeting.id}/status"
    done = await client.post(path, json={"status": "no_show"}, headers=_h(specialist))
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "no_show"

    stranger = await _user(db_session, UserRole.psychologist)
    assert (await client.post(path, json={"status": "done"}, headers=_h(stranger))).status_code == 404


# ── cancel, move ────────────────────────────────────────────────────────────


async def test_owner_cancels_with_reason_and_time_is_free_again(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    specialist = await _user(db_session, UserRole.psychologist)
    owner = await _user(db_session, UserRole.owner)
    deal, meeting = await _booked(client, db_session, manager, specialist)
    path = f"{URL}/meetings/{meeting['id']}/cancel"

    assert (await client.post(path, json={"reason": "Клиент заболел"}, headers=_h(manager))).status_code == 403
    assert (await client.post(path, json={"reason": ""}, headers=_h(owner))).status_code == 422
    cancelled = await client.post(path, json={"reason": "Клиент заболел"}, headers=_h(owner))
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled" and cancelled.json()["cancel_reason"] == "Клиент заболел"

    slot = await db_session.scalar(select(SpecialistSlot).where(SpecialistSlot.specialist_id == specialist.id))
    assert slot.state == SlotState.free and slot.meeting_id is None
    card = (await client.get(f"{URL}/deals/{deal['id']}", headers=_h(manager))).json()
    assert card["meeting"] is None
    assert card["events"][0]["kind"] == "meeting_cancelled"
    # The deal can be booked again.
    again = await client.post(
        f"{URL}/deals/{deal['id']}/booking", json={"start": meeting["start"], "handoff": _handoff()}, headers=_h(manager)
    )
    assert again.status_code == 200, again.text


async def test_move_keeps_specialist_when_free(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    specialist = await _user(db_session, UserRole.psychologist)
    owner = await _user(db_session, UserRole.owner)
    deal, meeting = await _booked(client, db_session, manager, specialist)
    later = await _open_slots(db_session, specialist, FUTURE_DAY, time(15, 0), 1)
    # Another specialist is free then too; the moved call still stays.
    await _open_slots(db_session, await _user(db_session, UserRole.psychologist), FUTURE_DAY, time(15, 0), 1)

    moved = await client.post(
        f"{URL}/meetings/{meeting['id']}/reschedule",
        json={"start": _iso(later), "reason": "Родитель просит позже"},
        headers=_h(owner),
    )
    assert moved.status_code == 200, moved.text
    body = moved.json()
    assert body["id"] != meeting["id"] and body["rescheduled_from_id"] == meeting["id"]
    assert body["specialist"]["id"] == str(specialist.id)
    assert body["handoff"]["family_request"] == _handoff()["family_request"]
    assert body["history"][0]["action"] == "meeting.rescheduled"

    old = await db_session.get(Meeting, uuid.UUID(meeting["id"]))
    await db_session.refresh(old)
    assert old.status == MeetingStatus.cancelled and old.cancel_reason == "Родитель просит позже"
    slots = {
        s.start_at: s.state
        for s in (
            await db_session.execute(select(SpecialistSlot).where(SpecialistSlot.specialist_id == specialist.id))
        ).scalars()
    }
    assert slots[later] == SlotState.booked
    assert list(slots.values()).count(SlotState.free) == 1

    entries = (await db_session.execute(select(AuditLog).where(AuditLog.action == "meeting.rescheduled"))).scalars()
    assert any(e.reason == "Родитель просит позже" for e in entries)


async def test_move_to_taken_time_changes_nothing(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    specialist = await _user(db_session, UserRole.psychologist)
    owner = await _user(db_session, UserRole.owner)
    deal, meeting = await _booked(client, db_session, manager, specialist)
    nobody_free = tz.at(FUTURE_DAY, time(18, 0))
    moved = await client.post(
        f"{URL}/meetings/{meeting['id']}/reschedule",
        json={"start": _iso(nobody_free), "reason": "Перенос"},
        headers=_h(owner),
    )
    assert moved.json()["error_code"] == "slot_taken"
    still = (await client.get(f"{URL}/meetings/{meeting['id']}", headers=_h(owner))).json()
    assert still["status"] == "pending"


async def test_manager_asks_owner_to_move(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    specialist = await _user(db_session, UserRole.psychologist)
    await _user(db_session, UserRole.owner)
    deal, meeting = await _booked(client, db_session, manager, specialist)
    asked = await client.post(
        f"{URL}/meetings/{meeting['id']}/reschedule-request",
        json={"comment": "Клиент просит на пятницу"},
        headers=_h(manager),
    )
    assert asked.status_code == 201, asked.text
    assert asked.json()["type"] == "reschedule"
    # The earliest active owner gets it — on a fresh database, this one.
    assignee = await db_session.get(User, uuid.UUID(asked.json()["assignee"]["id"]))
    assert assignee.role == UserRole.owner
    owner_tasks = (await client.get(f"{URL}/tasks", headers=_h(assignee))).json()
    assert asked.json()["id"] in [t["id"] for t in owner_tasks]
    assert (await client.get(f"{URL}/tasks", headers=_h(manager))).json() == []


# ── tasks ───────────────────────────────────────────────────────────────────


async def test_manager_sets_tasks_only_for_self(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User, head: User
) -> None:
    deal = await _create(client, manager)
    due = _iso(tz.now_utc() + timedelta(hours=3))
    forbidden = await client.post(
        f"{URL}/tasks", json={"deal_id": deal["id"], "text": "Позвонить", "due_at": due, "assignee_id": str(head.id)},
        headers=_h(manager),
    )
    assert forbidden.status_code == 403

    task = await client.post(f"{URL}/tasks", json={"deal_id": deal["id"], "text": "Позвонить", "due_at": due},
                             headers=_h(manager))
    assert task.status_code == 201 and task.json()["assignee"]["id"] == str(manager.id)
    assert task.json()["deal_title"] == "Асель Нурланова · Камила"

    board = (await client.get(f"{URL}/deals", headers=_h(manager))).json()
    assert next(d for d in board if d["id"] == deal["id"])["next_task_due"] is not None

    # The head of sales gives the manager a task; the manager sees it.
    given = await client.post(
        f"{URL}/tasks", json={"deal_id": deal["id"], "text": "Дожать", "due_at": due, "assignee_id": str(manager.id)},
        headers=_h(head),
    )
    assert given.status_code == 201
    mine = (await client.get(f"{URL}/tasks", headers=_h(manager))).json()
    assert {t["text"] for t in mine} >= {"Позвонить", "Дожать"}

    other = await _user(db_session, UserRole.sales_manager)
    assert (await client.post(f"{URL}/tasks/{task.json()['id']}/done", json={}, headers=_h(other))).status_code == 404

    done = await client.post(f"{URL}/tasks/{task.json()['id']}/done", json={"result": "Договорились на завтра"},
                             headers=_h(manager))
    assert done.json()["done_at"] is not None
    card = (await client.get(f"{URL}/deals/{deal['id']}", headers=_h(manager))).json()
    assert [t["text"] for t in card["tasks"]] == ["Дожать", "Позвонить"]
    assert card["events"][0]["kind"] == "task_done"
    again = await client.post(f"{URL}/tasks/{task.json()['id']}/done", json={}, headers=_h(manager))
    assert again.json()["error_code"] == "task_already_done"


# ── filters ─────────────────────────────────────────────────────────────────


async def test_search_and_filters(client: httpx.AsyncClient, db_session: AsyncSession, manager: User) -> None:
    deal = await _create(client, manager)
    phone_tail = deal["parent"]["phone"][-7:]
    found = (await client.get(f"{URL}/deals", params={"q": phone_tail}, headers=_h(manager))).json()
    assert [d["id"] for d in found] == [deal["id"]]
    by_name = (await client.get(f"{URL}/deals", params={"q": "камила"}, headers=_h(manager))).json()
    assert deal["id"] in [d["id"] for d in by_name]
    assert (await client.get(f"{URL}/deals", params={"stage": "invoice", "q": phone_tail},
                             headers=_h(manager))).json() == []
    unpaid = (await client.get(f"{URL}/deals", params={"paid": "false", "q": phone_tail}, headers=_h(manager))).json()
    assert len(unpaid) == 1
    mine = (await client.get(f"{URL}/deals", params={"manager": str(manager.id), "q": phone_tail},
                             headers=_h(manager))).json()
    assert len(mine) == 1
    assert (await client.get(f"{URL}/deals", params={"manager": "bogus"}, headers=_h(manager))).status_code == 422


async def test_clients_and_card_extras(client: httpx.AsyncClient, db_session: AsyncSession, manager: User) -> None:
    specialist = await _user(db_session, UserRole.psychologist)
    deal, meeting = await _booked(client, db_session, manager, specialist)
    card = (await client.get(f"{URL}/deals/{deal['id']}", headers=_h(manager))).json()
    assert card["stage_at"] >= card["created_at"]

    rows = (await client.get(f"{URL}/clients", params={"q": deal["parent"]["phone"][-7:]}, headers=_h(manager))).json()
    assert len(rows) == 1
    row = rows[0]
    assert row["students"] == ["Камила Нурланова"]
    assert row["deals"] == 1 and row["meetings_total"] == 1 and row["paid_total"] == 45000
    other = await _user(db_session, UserRole.sales_manager)
    assert (await client.get(f"{URL}/clients", params={"q": deal["parent"]["phone"][-7:]},
                             headers=_h(other))).json() == []
