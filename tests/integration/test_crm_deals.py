"""CRM deals board and booking against docs/frontend-crm-api-contract.md."""

import uuid
from datetime import date, datetime, time, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduling import Meeting, SlotState, SpecialistSlot
from app.models.user import User, UserRole
from app.services import auth_service, tz

URL = "/api/v1/crm"


async def _user(db: AsyncSession, role: UserRole, full_name: str | None = None) -> User:
    user = User(
        email=f"{uuid.uuid4()}@example.test",
        hashed_password=auth_service.hash_password("Testpass123!"),
        is_active=True,
        is_verified=True,
        role=role,
        full_name=full_name,
    )
    db.add(user)
    await db.flush()
    return user


def _h(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_service.create_jwt_token(user)}"}


def _phone() -> str:
    return "8 (701) " + str(uuid.uuid4().int)[:7]


@pytest.fixture
async def manager(db_session: AsyncSession, price_list: None) -> User:
    return await _user(db_session, UserRole.sales_manager, "Айгерим")


@pytest.fixture
async def head(db_session: AsyncSession, price_list: None) -> User:
    return await _user(db_session, UserRole.sales_head, "Бахтияр")


async def _create(client: httpx.AsyncClient, user: User, **extra) -> dict:
    body = {"parent": {"full_name": "Асель Нурланова", "phone": _phone()}, "student": {"full_name": "Камила"}, **extra}
    response = await client.post(f"{URL}/deals", json=body, headers=_h(user))
    assert response.status_code == 201, response.text
    return response.json()


async def _ready_to_book(client: httpx.AsyncClient, user: User, tariff: str = "package") -> dict:
    deal = await _create(client, user)
    path = f"{URL}/deals/{deal['id']}"
    assert (await client.patch(path, json={"is_target": True, "tariff_code": tariff}, headers=_h(user))).status_code == 200
    paid = await client.post(f"{path}/payment", json={"amount": 45000, "method": "transfer"}, headers=_h(user))
    assert paid.status_code == 200, paid.text
    assert (await client.post(f"{path}/consent", json={"given": True}, headers=_h(user))).status_code == 200
    return paid.json()


async def _open_slots(db: AsyncSession, specialist: User, day: date, start: time, count: int) -> datetime:
    first = tz.at(day, start)
    for i in range(count):
        db.add(SpecialistSlot(specialist_id=specialist.id, start_at=first + timedelta(minutes=30 * i), state=SlotState.free))
    await db.flush()
    return first


def _handoff() -> dict:
    return {
        "student_name": "Камила Нурланова",
        "age": 15,
        "gender": "female",
        "grade": 9,
        "study_language": "ru",
        "russian_level": "fluent",
        "family_request": "Выбор профиля в 10 классе",
        "parent_participates": True,
        "contact": "parent",
        "contact_phone": "+77011234567",
    }


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


FUTURE_DAY = tz.today() + timedelta(days=10)


# ── creating, inbox, duplicates ─────────────────────────────────────────────


async def test_manager_lead_goes_to_qualification_owner_lead_to_inbox(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    mine = await _create(client, manager)
    assert mine["stage"] == "qualification"
    assert mine["manager"]["id"] == str(manager.id)
    assert mine["parent"]["phone"].startswith("+7701")

    owner = await _user(db_session, UserRole.owner)
    inbox = await _create(client, owner)
    assert inbox["stage"] == "unsorted" and inbox["manager"] is None

    other = await _user(db_session, UserRole.sales_manager)
    accepted = await client.post(f"{URL}/deals/{inbox['id']}/accept", headers=_h(other))
    assert accepted.json()["stage"] == "qualification"
    again = await client.post(f"{URL}/deals/{inbox['id']}/accept", headers=_h(manager))
    assert again.status_code == 404  # now someone else's deal


async def test_duplicate_phone_offers_existing_client(client: httpx.AsyncClient, manager: User) -> None:
    first = await _create(client, manager)
    phone = first["parent"]["phone"]
    dup = await client.post(
        f"{URL}/deals", json={"parent": {"full_name": "Другое имя", "phone": phone.replace("+7", "8")}}, headers=_h(manager)
    )
    assert dup.status_code == 409
    assert dup.json()["error_code"] == "parent_exists"
    assert dup.json()["parent_id"] == first["parent"]["id"]

    found = await client.get(f"{URL}/parents", params={"phone": phone}, headers=_h(manager))
    assert found.json()[0]["open_deal_id"] == first["id"]

    added = await client.post(f"{URL}/deals", json={"parent_id": first["parent"]["id"]}, headers=_h(manager))
    assert added.status_code == 201


# ── access ──────────────────────────────────────────────────────────────────


async def test_manager_sees_only_own_and_inbox(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User, head: User
) -> None:
    other = await _user(db_session, UserRole.sales_manager)
    theirs = await _create(client, other)
    mine = await _create(client, manager)

    ids = {d["id"] for d in (await client.get(f"{URL}/deals", headers=_h(manager))).json()}
    assert mine["id"] in ids and theirs["id"] not in ids
    assert (await client.get(f"{URL}/deals/{theirs['id']}", headers=_h(manager))).status_code == 404

    head_ids = {d["id"] for d in (await client.get(f"{URL}/deals", headers=_h(head))).json()}
    assert {mine["id"], theirs["id"]} <= head_ids


async def test_marketer_sees_board_without_personal_data(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    deal = await _create(client, manager)
    marketer = await _user(db_session, UserRole.marketer)
    board = await client.get(f"{URL}/deals", headers=_h(marketer))
    card = next(d for d in board.json() if d["id"] == deal["id"])
    assert card["parent_name"] is None and card["phone"] is None and card["student_name"] is None
    assert "Асель" not in board.text
    assert (await client.get(f"{URL}/deals/{deal['id']}", headers=_h(marketer))).status_code == 403
    assert (await client.post(f"{URL}/deals", json={}, headers=_h(marketer))).status_code == 403


# ── funnel rules ────────────────────────────────────────────────────────────


async def test_stage_rules(client: httpx.AsyncClient, manager: User, head: User) -> None:
    deal = await _create(client, manager)
    path = f"{URL}/deals/{deal['id']}"

    async def move(stage: str, user: User = manager) -> httpx.Response:
        return await client.post(f"{path}/stage", json={"stage": stage}, headers=_h(user))

    assert (await move("consultation")).json()["error_code"] == "deal_target_required"
    await client.patch(path, json={"is_target": False, "non_target_reason": "не та аудитория"}, headers=_h(manager))
    assert (await move("closing")).json()["error_code"] == "deal_non_target"

    await client.patch(path, json={"is_target": True}, headers=_h(manager))
    assert (await move("closing")).status_code == 200
    assert (await move("invoice")).json()["error_code"] == "deal_tariff_required"
    assert (await move("paid")).json()["error_code"] == "stage_paid_via_payment"

    await client.patch(path, json={"tariff_code": "package"}, headers=_h(manager))
    assert (await move("invoice")).status_code == 200
    assert (await move("qualification")).status_code == 200  # back and forth within 1–5
    await client.post(f"{path}/payment", json={"amount": 70000, "method": "cash"}, headers=_h(manager))
    detail = (await client.get(path, headers=_h(manager))).json()
    assert detail["stage"] == "paid"
    assert [e["kind"] for e in detail["events"]][:2] == ["payment", "stage"]

    assert (await move("closing")).json()["error_code"] == "deal_paid_stage_back"
    assert (await move("diagnostics_done")).status_code == 403
    assert (await move("diagnostics_done", head)).status_code == 200


async def test_price_is_fixed_and_discount_journaled(
    client: httpx.AsyncClient, manager: User, head: User
) -> None:
    deal = await _create(client, manager)
    path = f"{URL}/deals/{deal['id']}"
    patched = await client.patch(path, json={"is_target": True, "tariff_code": "testing", "discount": 5000}, headers=_h(manager))
    assert patched.json()["price"] == 45000 and patched.json()["total"] == 40000

    await client.post(f"{path}/payment", json={"amount": 40000, "method": "cash"}, headers=_h(manager))
    locked = await client.patch(path, json={"discount": 10000}, headers=_h(manager))
    assert locked.json()["error_code"] == "deal_paid_locked"
    assert (await client.patch(path, json={"discount": 10000}, headers=_h(head))).json()["total"] == 35000
    changed = await client.post(f"{path}/payment", json={"amount": 35000, "method": "cash"}, headers=_h(manager))
    assert changed.json()["error_code"] == "payment_change_forbidden"


async def test_closing_rules(client: httpx.AsyncClient, manager: User, head: User) -> None:
    deal = await _create(client, manager)
    path = f"{URL}/deals/{deal['id']}"
    no_reason = await client.post(f"{path}/close", json={"result": "lost"}, headers=_h(manager))
    assert no_reason.json()["error_code"] == "close_reason_required"
    win = await client.post(f"{path}/close", json={"result": "won"}, headers=_h(manager))
    assert win.status_code == 403

    lost = await client.post(f"{path}/close", json={"result": "lost", "reason": "no_answer"}, headers=_h(manager))
    assert lost.json()["result"] == "lost"
    ids = {d["id"] for d in (await client.get(f"{URL}/deals", headers=_h(manager))).json()}
    assert deal["id"] not in ids  # closed deals leave the board
    lost_ids = {d["id"] for d in (await client.get(f"{URL}/deals?result=lost", headers=_h(manager))).json()}
    assert deal["id"] in lost_ids

    paid = await _ready_to_book(client, manager)
    forbidden = await client.post(
        f"{URL}/deals/{paid['id']}/close", json={"result": "lost", "reason": "refund"}, headers=_h(manager)
    )
    assert forbidden.status_code == 403
    # «Успешно» only once the report is out, not right after the payment.
    early = await client.post(f"{URL}/deals/{paid['id']}/close", json={"result": "won"}, headers=_h(head))
    assert early.status_code == 409 and early.json()["error_code"] == "deal_win_too_early"
    moved = await client.post(f"{URL}/deals/{paid['id']}/stage", json={"stage": "report_published"}, headers=_h(head))
    assert moved.status_code == 200, moved.text
    won = await client.post(f"{URL}/deals/{paid['id']}/close", json={"result": "won"}, headers=_h(head))
    assert won.json()["result"] == "won"


# ── booking ─────────────────────────────────────────────────────────────────


async def test_booking_needs_payment_target_and_consent(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    specialist = await _user(db_session, UserRole.psychologist)
    start = await _open_slots(db_session, specialist, FUTURE_DAY, time(10, 0), 1)
    deal = await _create(client, manager)
    path = f"{URL}/deals/{deal['id']}"
    body = {"start": _iso(start), "handoff": _handoff()}
    assert (await client.post(f"{path}/booking", json=body, headers=_h(manager))).json()["error_code"] == "deal_not_paid"

    await client.patch(path, json={"is_target": True, "tariff_code": "package"}, headers=_h(manager))
    await client.post(f"{path}/payment", json={"amount": 45000, "method": "cash"}, headers=_h(manager))
    assert (await client.post(f"{path}/booking", json=body, headers=_h(manager))).json()["error_code"] == "consent_required"

    no_card = {"start": _iso(start), "handoff": {**_handoff(), "family_request": ""}}
    await client.post(f"{path}/consent", json={"given": True}, headers=_h(manager))
    assert (await client.post(f"{path}/booking", json=no_card, headers=_h(manager))).status_code == 422


async def test_booking_assigns_least_busy_specialist_and_hides_name_from_manager(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User, head: User
) -> None:
    busy = await _user(db_session, UserRole.psychologist, "Занятой")
    idle = await _user(db_session, UserRole.psychologist, "Свободный")
    start = await _open_slots(db_session, busy, FUTURE_DAY, time(11, 0), 1)
    await _open_slots(db_session, idle, FUTURE_DAY, time(11, 0), 1)
    # `busy` already has a meeting this week.
    earlier = await _open_slots(db_session, busy, FUTURE_DAY, time(9, 0), 1)
    first = await _ready_to_book(client, manager)
    await client.post(f"{URL}/deals/{first['id']}/booking", json={"start": _iso(earlier), "handoff": _handoff()}, headers=_h(manager))

    deal = await _ready_to_book(client, manager)
    booked = await client.post(f"{URL}/deals/{deal['id']}/booking", json={"start": _iso(start), "handoff": _handoff()}, headers=_h(manager))
    assert booked.status_code == 200, booked.text
    meeting = booked.json()["meeting"]
    assert meeting["type"] == "intro30" and meeting["specialist"] is None
    assert "Свободный" not in booked.text

    as_head = (await client.get(f"{URL}/deals/{deal['id']}", headers=_h(head))).json()
    assert as_head["meeting"]["specialist"]["name"] == "Свободный"

    slot = await db_session.get(SpecialistSlot, (idle.id, start))
    assert slot.state == SlotState.booked and str(slot.meeting_id) == meeting["id"]
    free = await client.get(f"/api/v1/scheduling/free?from={FUTURE_DAY}&to={FUTURE_DAY}", headers=_h(head))
    assert not any(s["start"] == _iso(start) and any(x["id"] == str(idle.id) for x in s["specialists"]) for s in free.json()["slots"])

    # The specialist cannot edit the booked slot, and sees the handoff card.
    edit = await client.patch(
        "/api/v1/scheduling/specialists/me/availability",
        json={"changes": [{"start": _iso(start), "end": _iso(start + timedelta(minutes=30)), "state": "closed"}]},
        headers=_h(idle),
    )
    assert edit.status_code == 409 and edit.json()["error_code"] == "slot_booked"
    meetings = await client.get(
        f"/api/v1/scheduling/specialists/me/meetings?from={FUTURE_DAY}&to={FUTURE_DAY}", headers=_h(idle)
    )
    card = meetings.json()[0]["handoff"]
    assert card["student_name"] == "Камила Нурланова" and card["tariff"] == "Пакет"
    assert "45000" not in meetings.text

    again = await client.post(f"{URL}/deals/{deal['id']}/booking", json={"start": _iso(start), "handoff": _handoff()}, headers=_h(manager))
    assert again.json()["error_code"] == "deal_already_booked"


async def test_a_returning_client_goes_back_to_their_specialist_when_free(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User, head: User
) -> None:
    known = await _user(db_session, UserRole.psychologist, "Прежний")
    other = await _user(db_session, UserRole.psychologist, "Другой")
    earlier = await _open_slots(db_session, known, FUTURE_DAY, time(9, 0), 1)
    first = await _ready_to_book(client, manager)
    body = {"start": _iso(earlier), "handoff": _handoff()}
    assert (await client.post(f"{URL}/deals/{first['id']}/booking", json=body, headers=_h(manager))).status_code == 200

    async def again(start: datetime) -> dict:
        """The same family's next deal, booked at `start`."""
        created = await client.post(f"{URL}/deals", json={"parent_id": first["parent"]["id"]}, headers=_h(manager))
        assert created.status_code == 201, created.text
        path = f"{URL}/deals/{created.json()['id']}"
        assert (await client.patch(path, json={"is_target": True, "tariff_code": "package"}, headers=_h(manager))).status_code == 200
        assert (await client.post(f"{path}/payment", json={"amount": 45000, "method": "transfer"}, headers=_h(manager))).status_code == 200
        assert (await client.post(f"{path}/consent", json={"given": True}, headers=_h(manager))).status_code == 200
        booked = await client.post(f"{path}/booking", json={"start": _iso(start), "handoff": _handoff()}, headers=_h(manager))
        assert booked.status_code == 200, booked.text
        assert booked.json()["meeting"]["specialist"] is None  # still no names for the manager
        return (await client.get(path, headers=_h(head))).json()["meeting"]["specialist"]

    # Both free and `other` less busy this week — the family's specialist still wins.
    both = await _open_slots(db_session, known, FUTURE_DAY, time(11, 0), 1)
    await _open_slots(db_session, other, FUTURE_DAY, time(11, 0), 1)
    assert (await again(both))["name"] == "Прежний"

    # Not free at the chosen time: the usual pick.
    only_other = await _open_slots(db_session, other, FUTURE_DAY, time(14, 0), 1)
    assert (await again(only_other))["name"] == "Другой"


async def test_last_slot_goes_to_one_booking_only(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    specialist = await _user(db_session, UserRole.psychologist)
    start = await _open_slots(db_session, specialist, FUTURE_DAY, time(15, 0), 1)
    a = await _ready_to_book(client, manager)
    b = await _ready_to_book(client, manager)
    body = {"start": _iso(start), "handoff": _handoff()}
    first = await client.post(f"{URL}/deals/{a['id']}/booking", json=body, headers=_h(manager))
    second = await client.post(f"{URL}/deals/{b['id']}/booking", json=body, headers=_h(manager))
    assert first.status_code == 200
    assert second.status_code == 409 and second.json()["error_code"] == "slot_taken"


async def test_the_crm_books_a_thirty_minute_first_call_for_any_tariff(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    """The manager books the first call — 30 minutes whatever the tariff; the
    60-minute second one the specialist sets (second_meeting)."""
    specialist = await _user(db_session, UserRole.psychologist)
    start = await _open_slots(db_session, specialist, FUTURE_DAY, time(17, 0), 1)
    deal = await _ready_to_book(client, manager, tariff="package")
    booked = await client.post(
        f"{URL}/deals/{deal['id']}/booking", json={"start": _iso(start), "handoff": _handoff()}, headers=_h(manager)
    )
    assert booked.status_code == 200, booked.text
    meeting = await db_session.scalar(select(Meeting).where(Meeting.deal_id == uuid.UUID(deal["id"])))
    assert meeting.type.value == "intro30" and meeting.end_at - meeting.start_at == timedelta(minutes=30)
