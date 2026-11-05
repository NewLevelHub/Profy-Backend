"""CRM deals board and booking against docs/frontend-crm-api-contract.md."""

import uuid
from datetime import date, datetime, time, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult, ReviewStatus
from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.crm import CrmDeal, CrmDealEvent, DealResult, DealStage
from app.models.profile import Profile
from app.models.psychologist_assignment import PsychologistStudentAssignment
from app.models.scheduling import Meeting, MeetingStatus, SlotState, SpecialistSlot
from app.models.user import User, UserRole
from app.services import auth_service, tz
from app.services.crm import closing, invites, reassign

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
    assert meeting["type"] == "intro30" and meeting["specialist"]["name"] == "Свободный"

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


async def test_booking_takes_the_chosen_specialist_over_the_system_pick(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    busy = await _user(db_session, UserRole.psychologist, "Занятой")
    idle = await _user(db_session, UserRole.psychologist, "Свободный")
    # The system would take `idle`: `busy` already has a meeting this week.
    earlier = await _open_slots(db_session, busy, FUTURE_DAY, time(9, 0), 1)
    first = await _ready_to_book(client, manager)
    body = {"start": _iso(earlier), "handoff": _handoff()}
    assert (await client.post(f"{URL}/deals/{first['id']}/booking", json=body, headers=_h(manager))).status_code == 200
    start = await _open_slots(db_session, busy, FUTURE_DAY, time(11, 0), 1)
    await _open_slots(db_session, idle, FUTURE_DAY, time(11, 0), 1)

    deal = await _ready_to_book(client, manager)
    body = {"start": _iso(start), "handoff": _handoff(), "specialist_id": str(busy.id)}
    booked = await client.post(f"{URL}/deals/{deal['id']}/booking", json=body, headers=_h(manager))
    assert booked.status_code == 200, booked.text
    assert booked.json()["meeting"]["specialist"]["name"] == "Занятой"
    assert (await db_session.get(SpecialistSlot, (busy.id, start))).state == SlotState.booked
    assert (await db_session.get(SpecialistSlot, (idle.id, start))).state == SlotState.free


async def test_booking_a_chosen_specialist_who_is_not_free_changes_nothing(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    chosen = await _user(db_session, UserRole.psychologist, "Выбранный")
    other = await _user(db_session, UserRole.psychologist, "Другой")
    start = await _open_slots(db_session, other, FUTURE_DAY, time(11, 0), 1)

    deal = await _ready_to_book(client, manager)
    body = {"start": _iso(start), "handoff": _handoff(), "specialist_id": str(chosen.id)}
    taken = await client.post(f"{URL}/deals/{deal['id']}/booking", json=body, headers=_h(manager))
    assert taken.status_code == 409
    assert taken.json()["error_code"] == "slot_taken"
    assert (await db_session.get(SpecialistSlot, (other.id, start))).state == SlotState.free


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


# ── changing the specialist ─────────────────────────────────────────────────


async def _booked_with(
    client: httpx.AsyncClient, db: AsyncSession, manager: User, specialist: User, at: time
) -> tuple[dict, datetime]:
    start = await _open_slots(db, specialist, FUTURE_DAY, at, 1)
    deal = await _ready_to_book(client, manager)
    body = {"start": _iso(start), "handoff": _handoff(), "specialist_id": str(specialist.id)}
    booked = await client.post(f"{URL}/deals/{deal['id']}/booking", json=body, headers=_h(manager))
    assert booked.status_code == 200, booked.text
    return booked.json(), start


async def _assigned(db: AsyncSession, specialist: User, student: User) -> bool:
    return bool(
        await db.scalar(
            select(PsychologistStudentAssignment.id).where(
                PsychologistStudentAssignment.psychologist_id == specialist.id,
                PsychologistStudentAssignment.student_id == student.id,
            )
        )
    )


async def test_changing_the_specialist_moves_the_call_and_the_student(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    old = await _user(db_session, UserRole.psychologist, "Прежний")
    new = await _user(db_session, UserRole.psychologist, "Новый")
    student = await _user(db_session, UserRole.student)
    deal, start = await _booked_with(client, db_session, manager, old, time(10, 0))
    await _open_slots(db_session, new, FUTURE_DAY, time(10, 0), 1)
    row = await db_session.get(CrmDeal, uuid.UUID(deal["id"]))
    row.student_user_id = student.id
    db_session.add(PsychologistStudentAssignment(psychologist_id=old.id, student_id=student.id))
    await db_session.flush()

    options = await client.get(f"{URL}/deals/{deal['id']}/specialists", headers=_h(manager))
    assert {"id": str(new.id), "name": "Новый", "available": True} in options.json()
    assert str(old.id) not in options.text

    body = {"specialist_id": str(new.id), "reason": "Болезнь"}
    changed = await client.post(f"{URL}/deals/{deal['id']}/specialist", json=body, headers=_h(manager))
    assert changed.status_code == 200, changed.text
    out = changed.json()
    assert out["specialist"]["name"] == "Новый"
    assert out["meeting"]["id"] == deal["meeting"]["id"] and out["meeting"]["specialist"]["name"] == "Новый"
    assert out["events"][0]["kind"] == "specialist_changed"
    assert out["events"][0]["data"] == {"from": "Прежний", "to": "Новый"} and out["events"][0]["text"] == "Болезнь"

    freed = await db_session.get(SpecialistSlot, (old.id, start))
    taken = await db_session.get(SpecialistSlot, (new.id, start))
    await db_session.refresh(freed)
    await db_session.refresh(taken)
    assert freed.state == SlotState.free and freed.meeting_id is None
    assert taken.state == SlotState.booked and str(taken.meeting_id) == deal["meeting"]["id"]
    assert await _assigned(db_session, new, student) and not await _assigned(db_session, old, student)


async def test_changing_to_a_busy_specialist_changes_nothing(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    old = await _user(db_session, UserRole.psychologist, "Прежний")
    busy = await _user(db_session, UserRole.psychologist, "Занятой")
    deal, start = await _booked_with(client, db_session, manager, old, time(10, 0))

    options = (await client.get(f"{URL}/deals/{deal['id']}/specialists", headers=_h(manager))).json()
    assert next(o for o in options if o["id"] == str(busy.id))["available"] is False

    body = {"specialist_id": str(busy.id), "reason": "Болезнь"}
    refused = await client.post(f"{URL}/deals/{deal['id']}/specialist", json=body, headers=_h(manager))
    assert refused.status_code == 409 and refused.json()["error_code"] == "specialist_not_free"
    assert (await db_session.get(SpecialistSlot, (old.id, start))).state == SlotState.booked
    same = {"specialist_id": str(old.id), "reason": "Болезнь"}
    again = await client.post(f"{URL}/deals/{deal['id']}/specialist", json=same, headers=_h(manager))
    assert again.status_code == 409 and again.json()["error_code"] == "specialist_same"


async def test_a_begun_call_stays_with_the_old_specialist(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    old = await _user(db_session, UserRole.psychologist, "Прежний")
    new = await _user(db_session, UserRole.psychologist, "Новый")
    deal, start = await _booked_with(client, db_session, manager, old, time(10, 0))
    meeting = await db_session.get(Meeting, uuid.UUID(deal["meeting"]["id"]))
    past = tz.now_utc() - timedelta(days=1)
    meeting.start_at, meeting.end_at = past, past + timedelta(minutes=30)
    await db_session.flush()

    body = {"specialist_id": str(new.id), "reason": "Болезнь"}
    changed = await client.post(f"{URL}/deals/{deal['id']}/specialist", json=body, headers=_h(manager))
    assert changed.status_code == 200, changed.text
    assert changed.json()["specialist"]["name"] == "Новый"
    assert changed.json()["meetings"][0]["specialist"]["name"] == "Прежний"


async def test_after_a_begun_call_the_old_one_marks_it_and_the_new_one_sets_the_second(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    old = await _user(db_session, UserRole.psychologist, "Прежний")
    new = await _user(db_session, UserRole.psychologist, "Новый")
    student = await _user(db_session, UserRole.student)
    deal, _ = await _booked_with(client, db_session, manager, old, time(10, 0))
    await _link(db_session, deal, student)
    db_session.add(PsychologistStudentAssignment(psychologist_id=old.id, student_id=student.id))
    meeting = await db_session.get(Meeting, uuid.UUID(deal["meeting"]["id"]))
    past = tz.now_utc() - timedelta(hours=1)
    meeting.start_at, meeting.end_at = past, past + timedelta(minutes=30)
    await db_session.flush()

    body = {"specialist_id": str(new.id), "reason": "Болезнь"}
    assert (await client.post(f"{URL}/deals/{deal['id']}/specialist", json=body, headers=_h(manager))).status_code == 200
    assert await _holders(db_session, student) == ["Новый"]

    marked = await client.post(
        f"/api/v1/scheduling/specialists/me/meetings/{meeting.id}/status", json={"status": "done"}, headers=_h(old)
    )
    assert marked.status_code == 200, marked.text
    second = f"/api/v1/psychologist/students/{student.id}/second-meeting"
    assert (await client.get(second, headers=_h(old))).status_code == 404
    state = await client.get(second, headers=_h(new))
    assert state.status_code == 200 and state.json()["can_schedule"] is True


async def test_changing_the_specialist_needs_one_and_the_deal_owner(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    old = await _user(db_session, UserRole.psychologist, "Прежний")
    new = await _user(db_session, UserRole.psychologist, "Новый")
    body = {"specialist_id": str(new.id), "reason": "Болезнь"}
    unbooked = await _ready_to_book(client, manager)
    none = await client.post(f"{URL}/deals/{unbooked['id']}/specialist", json=body, headers=_h(manager))
    assert none.status_code == 409 and none.json()["error_code"] == "deal_no_specialist"

    deal, _ = await _booked_with(client, db_session, manager, old, time(10, 0))
    other = await _user(db_session, UserRole.sales_manager)
    assert (await client.post(f"{URL}/deals/{deal['id']}/specialist", json=body, headers=_h(other))).status_code == 404
    assert (await client.get(f"{URL}/deals/{deal['id']}/specialists", headers=_h(other))).status_code == 404
    short = {"specialist_id": str(new.id), "reason": "x"}
    assert (await client.post(f"{URL}/deals/{deal['id']}/specialist", json=short, headers=_h(manager))).status_code == 422


async def _holders(db: AsyncSession, student: User) -> list[str]:
    rows = await db.execute(
        select(User.full_name)
        .join(PsychologistStudentAssignment, PsychologistStudentAssignment.psychologist_id == User.id)
        .where(PsychologistStudentAssignment.student_id == student.id)
    )
    return sorted(row[0] for row in rows)


async def _link(db: AsyncSession, deal: dict, student: User, *, days_ago: int = 0) -> CrmDeal:
    """Ties the deal to the account; `days_ago` orders deals made in one transaction."""
    row = await db.get(CrmDeal, uuid.UUID(deal["id"]))
    row.student_user_id = student.id
    row.created_at = tz.now_utc() - timedelta(days=days_ago)
    await db.flush()
    return row


async def test_rebooking_with_another_specialist_leaves_only_them(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    x = await _user(db_session, UserRole.psychologist, "Икс")
    y = await _user(db_session, UserRole.psychologist, "Игрек")
    student = await _user(db_session, UserRole.student)
    deal, _ = await _booked_with(client, db_session, manager, x, time(10, 0))
    await _link(db_session, deal, student)
    db_session.add(PsychologistStudentAssignment(psychologist_id=x.id, student_id=student.id))
    await db_session.flush()

    cancelled = await client.post(f"{URL}/meetings/{deal['meeting']['id']}/cancel", json={"reason": "Болезнь"}, headers=_h(manager))
    assert cancelled.status_code == 200, cancelled.text
    assert await _holders(db_session, student) == ["Икс"]  # no one else yet

    start = await _open_slots(db_session, y, FUTURE_DAY, time(12, 0), 1)
    body = {"start": _iso(start), "handoff": _handoff(), "specialist_id": str(y.id)}
    assert (await client.post(f"{URL}/deals/{deal['id']}/booking", json=body, headers=_h(manager))).status_code == 200
    assert await _holders(db_session, student) == ["Игрек"]


async def test_moving_a_call_to_another_specialist_leaves_only_them(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    x = await _user(db_session, UserRole.psychologist, "Икс")
    y = await _user(db_session, UserRole.psychologist, "Игрек")
    student = await _user(db_session, UserRole.student)
    deal, _ = await _booked_with(client, db_session, manager, x, time(10, 0))
    await _link(db_session, deal, student)
    start = await _open_slots(db_session, y, FUTURE_DAY, time(12, 0), 1)

    body = {"start": _iso(start), "reason": "Просьба клиента"}
    moved = await client.post(f"{URL}/meetings/{deal['meeting']['id']}/reschedule", json=body, headers=_h(manager))
    assert moved.status_code == 200, moved.text
    assert await _holders(db_session, student) == ["Игрек"]


async def test_a_change_goes_to_all_the_students_served_deals(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    x = await _user(db_session, UserRole.psychologist, "Икс")
    y = await _user(db_session, UserRole.psychologist, "Игрек")
    student = await _user(db_session, UserRole.student)
    old, _ = await _booked_with(client, db_session, manager, x, time(10, 0))
    new, _ = await _booked_with(client, db_session, manager, x, time(11, 0))
    await _link(db_session, old, student, days_ago=2)
    await _link(db_session, new, student)
    await _open_slots(db_session, y, FUTURE_DAY, time(10, 0), 1)
    await _open_slots(db_session, y, FUTURE_DAY, time(11, 0), 1)

    # Asked on the earlier deal: the later one and both calls follow.
    body = {"specialist_id": str(y.id), "reason": "Болезнь"}
    changed = await client.post(f"{URL}/deals/{old['id']}/specialist", json=body, headers=_h(manager))
    assert changed.status_code == 200, changed.text
    for deal in (old, new):
        out = (await client.get(f"{URL}/deals/{deal['id']}", headers=_h(manager))).json()
        assert out["specialist"]["name"] == "Игрек" and out["meeting"]["specialist"]["name"] == "Игрек"
    assert await _holders(db_session, student) == ["Игрек"]


async def test_a_change_needs_the_new_specialist_free_for_every_deals_call(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    x = await _user(db_session, UserRole.psychologist, "Икс")
    y = await _user(db_session, UserRole.psychologist, "Игрек")
    student = await _user(db_session, UserRole.student)
    old, _ = await _booked_with(client, db_session, manager, x, time(10, 0))
    new, _ = await _booked_with(client, db_session, manager, x, time(11, 0))
    await _link(db_session, old, student, days_ago=2)
    await _link(db_session, new, student)
    await _open_slots(db_session, y, FUTURE_DAY, time(11, 0), 1)  # free for one of the two

    options = (await client.get(f"{URL}/deals/{new['id']}/specialists", headers=_h(manager))).json()
    assert next(o for o in options if o["id"] == str(y.id))["available"] is False
    body = {"specialist_id": str(y.id), "reason": "Болезнь"}
    refused = await client.post(f"{URL}/deals/{new['id']}/specialist", json=body, headers=_h(manager))
    assert refused.status_code == 409 and refused.json()["error_code"] == "specialist_not_free"
    assert (await client.get(f"{URL}/deals/{new['id']}", headers=_h(manager))).json()["specialist"]["name"] == "Икс"


async def test_a_finished_earlier_deal_keeps_its_specialist(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    x = await _user(db_session, UserRole.psychologist, "Икс")
    y = await _user(db_session, UserRole.psychologist, "Игрек")
    student = await _user(db_session, UserRole.student)
    old, _ = await _booked_with(client, db_session, manager, x, time(10, 0))
    new, _ = await _booked_with(client, db_session, manager, x, time(11, 0))
    finished = await _link(db_session, old, student, days_ago=30)
    finished.result = DealResult.won
    call = await db_session.get(Meeting, uuid.UUID(old["meeting"]["id"]))
    call.start_at = tz.now_utc() - timedelta(days=20)
    call.end_at = call.start_at + timedelta(minutes=30)
    await _link(db_session, new, student)
    await _open_slots(db_session, y, FUTURE_DAY, time(11, 0), 1)

    body = {"specialist_id": str(y.id), "reason": "Болезнь"}
    assert (await client.post(f"{URL}/deals/{new['id']}/specialist", json=body, headers=_h(manager))).status_code == 200
    await db_session.refresh(finished)
    assert finished.specialist_id == x.id
    assert await _holders(db_session, student) == ["Игрек"]


async def test_an_invite_opened_after_the_change_leads_to_the_new_specialist(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    x = await _user(db_session, UserRole.psychologist, "Икс")
    y = await _user(db_session, UserRole.psychologist, "Игрек")
    student = await _user(db_session, UserRole.student)
    deal, _ = await _booked_with(client, db_session, manager, x, time(10, 0))
    await _open_slots(db_session, y, FUTURE_DAY, time(10, 0), 1)
    made = await client.post(f"{URL}/deals/{deal['id']}/invite", headers=_h(manager))
    assert made.status_code == 200, made.text
    url = made.json()["student_account"]["invite_url"]

    body = {"specialist_id": str(y.id), "reason": "Болезнь"}
    changed = await client.post(f"{URL}/deals/{deal['id']}/specialist", json=body, headers=_h(manager))
    assert changed.json()["student_account"]["invite_url"] == url  # the same link stays valid

    await invites.accept_invite(db_session, student, url.split("#token=")[1])
    assert await _holders(db_session, student) == ["Игрек"]


async def test_opening_an_invite_with_an_earlier_specialist_leaves_only_the_new_deals(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    x = await _user(db_session, UserRole.psychologist, "Икс")
    y = await _user(db_session, UserRole.psychologist, "Игрек")
    student = await _user(db_session, UserRole.student)
    old, _ = await _booked_with(client, db_session, manager, x, time(10, 0))
    finished = await _link(db_session, old, student, days_ago=30)
    finished.result = DealResult.won
    call = await db_session.get(Meeting, uuid.UUID(old["meeting"]["id"]))
    call.start_at = tz.now_utc() - timedelta(days=20)
    call.end_at = call.start_at + timedelta(minutes=30)
    db_session.add(PsychologistStudentAssignment(psychologist_id=x.id, student_id=student.id))
    await db_session.flush()

    new, _ = await _booked_with(client, db_session, manager, y, time(12, 0))
    made = await client.post(f"{URL}/deals/{new['id']}/invite", headers=_h(manager))
    await invites.accept_invite(db_session, student, made.json()["student_account"]["invite_url"].split("#token=")[1])
    assert await _holders(db_session, student) == ["Игрек"]


async def test_tying_a_deal_to_another_account_takes_the_specialist_off_the_first(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    x = await _user(db_session, UserRole.psychologist, "Икс")
    first = await _user(db_session, UserRole.student)
    second = await _user(db_session, UserRole.student)
    deal, _ = await _booked_with(client, db_session, manager, x, time(10, 0))
    for student in (first, second):
        made = await client.post(f"{URL}/deals/{deal['id']}/invite", headers=_h(manager))
        await invites.accept_invite(db_session, student, made.json()["student_account"]["invite_url"].split("#token=")[1])
    assert await _holders(db_session, first) == []
    assert await _holders(db_session, second) == ["Икс"]


async def test_the_new_specialist_is_told_also_of_a_waiting_report(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []

    async def handover(to: str, *_: object, **__: object) -> None:
        sent.append(f"handover:{to}")

    async def waiting(_db: object, *, student_id: uuid.UUID, **__: object) -> None:
        sent.append(f"report:{student_id}")

    monkeypatch.setattr(reassign.email_service, "send_student_handover_email", handover)
    monkeypatch.setattr(reassign.psychologist_service, "notify_review_pending", waiting)
    x = await _user(db_session, UserRole.psychologist, "Икс")
    y = await _user(db_session, UserRole.psychologist, "Игрек")
    student = await _user(db_session, UserRole.student)
    deal, _ = await _booked_with(client, db_session, manager, x, time(10, 0))
    await _link(db_session, deal, student)
    await _open_slots(db_session, y, FUTURE_DAY, time(10, 0), 1)
    profile = Profile(
        user_id=student.id, name="Камила", age=15, grade=9, city="Алматы", country="KZ", language="ru", age_group="senior"
    )
    db_session.add(profile)
    await db_session.flush()
    assessment = Assessment(profile_id=profile.id, status=AssessmentStatus.completed, goal=AssessmentGoal.explore)
    db_session.add(assessment)
    await db_session.flush()
    db_session.add(AnalysisResult(assessment_id=assessment.id, summary="-", review_status=ReviewStatus.pending_review))
    await db_session.flush()

    body = {"specialist_id": str(y.id), "reason": "Болезнь"}
    assert (await client.post(f"{URL}/deals/{deal['id']}/specialist", json=body, headers=_h(manager))).status_code == 200
    assert sent == [f"handover:{y.email}", f"report:{student.id}"]


async def _two_deals(
    client: httpx.AsyncClient, db: AsyncSession, manager: User
) -> tuple[dict, dict, User, User, User]:
    """The student's earlier deal with X, the later one with Y: only Y has them."""
    x = await _user(db, UserRole.psychologist, "Икс")
    y = await _user(db, UserRole.psychologist, "Игрек")
    student = await _user(db, UserRole.student)
    old, _ = await _booked_with(client, db, manager, x, time(9, 0))
    earlier = await _link(db, old, student, days_ago=9)
    earlier.result = DealResult.won
    call = await db.get(Meeting, uuid.UUID(old["meeting"]["id"]))
    call.start_at = tz.now_utc() - timedelta(days=9)
    call.end_at = call.start_at + timedelta(minutes=30)
    db.add(PsychologistStudentAssignment(psychologist_id=x.id, student_id=student.id))
    await db.flush()
    new, _ = await _booked_with(client, db, manager, y, time(12, 0))
    made = await client.post(f"{URL}/deals/{new['id']}/invite", headers=_h(manager))
    await invites.accept_invite(db, student, made.json()["student_account"]["invite_url"].split("#token=")[1])
    assert await _holders(db, student) == ["Игрек"]
    return old, new, x, y, student


async def test_closing_the_later_deal_returns_the_student_to_the_earlier_specialist(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User, head: User
) -> None:
    _, new, _, _, student = await _two_deals(client, db_session, manager)
    body = {"result": "lost", "reason": "refused"}
    closed = await client.post(f"{URL}/deals/{new['id']}/close", json=body, headers=_h(head))
    assert closed.status_code == 200, closed.text
    assert await _holders(db_session, student) == ["Икс"]


async def _call_state(db: AsyncSession, meeting_id: str) -> tuple[MeetingStatus, str | None]:
    row = (await db.execute(select(Meeting.status, Meeting.cancel_reason).where(Meeting.id == uuid.UUID(meeting_id)))).one()
    return row.status, row.cancel_reason


async def test_closing_as_lost_cancels_the_call_ahead_and_frees_its_time(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User, head: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[tuple[str, str]] = []

    async def cancelled(to: str, student: str, *_: object, **__: object) -> None:
        sent.append((to, student))

    monkeypatch.setattr(closing.email_service, "send_call_cancelled_email", cancelled)
    x = await _user(db_session, UserRole.psychologist, "Икс")
    deal, start = await _booked_with(client, db_session, manager, x, time(10, 0))
    meeting_id = deal["meeting"]["id"]

    body = {"result": "lost", "reason": "refused", "comment": "Передумали"}
    closed = await client.post(f"{URL}/deals/{deal['id']}/close", json=body, headers=_h(head))

    assert closed.status_code == 200, closed.text
    assert await _call_state(db_session, meeting_id) == (MeetingStatus.cancelled, "Сделка закрыта: Передумали")
    slot = (
        await db_session.execute(
            select(SpecialistSlot.state, SpecialistSlot.meeting_id).where(
                SpecialistSlot.specialist_id == x.id, SpecialistSlot.start_at == start
            )
        )
    ).one()
    assert (slot.state, slot.meeting_id) == (SlotState.free, None)
    assert sent == [(x.email, _handoff()["student_name"])]
    kinds = (await db_session.scalars(select(CrmDealEvent.kind).where(CrmDealEvent.deal_id == uuid.UUID(deal["id"])))).all()
    assert "meeting_cancelled" in kinds


async def test_closing_as_lost_leaves_a_started_call_as_it_is(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User, head: User
) -> None:
    x = await _user(db_session, UserRole.psychologist, "Икс")
    deal, _ = await _booked_with(client, db_session, manager, x, time(10, 0))
    meeting_id = deal["meeting"]["id"]
    call = await db_session.get(Meeting, uuid.UUID(meeting_id))
    call.start_at = tz.now_utc() - timedelta(minutes=5)
    call.end_at = call.start_at + timedelta(minutes=30)
    await db_session.flush()

    body = {"result": "lost", "reason": "refused"}
    assert (await client.post(f"{URL}/deals/{deal['id']}/close", json=body, headers=_h(head))).status_code == 200
    status, reason = await _call_state(db_session, meeting_id)
    assert status != MeetingStatus.cancelled and reason is None


async def test_closing_as_won_keeps_the_call_ahead(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User, head: User
) -> None:
    x = await _user(db_session, UserRole.psychologist, "Икс")
    deal, _ = await _booked_with(client, db_session, manager, x, time(10, 0))
    row = await db_session.get(CrmDeal, uuid.UUID(deal["id"]))
    row.stage = DealStage.report_published
    await db_session.flush()

    won = await client.post(f"{URL}/deals/{deal['id']}/close", json={"result": "won"}, headers=_h(head))
    assert won.status_code == 200, won.text
    status, _ = await _call_state(db_session, deal["meeting"]["id"])
    assert status != MeetingStatus.cancelled


async def test_closing_the_only_deal_takes_the_student_from_its_specialist(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User, head: User
) -> None:
    x = await _user(db_session, UserRole.psychologist, "Икс")
    student = await _user(db_session, UserRole.student)
    deal, _ = await _booked_with(client, db_session, manager, x, time(10, 0))
    await _link(db_session, deal, student)
    db_session.add(PsychologistStudentAssignment(psychologist_id=x.id, student_id=student.id))
    await db_session.flush()

    body = {"result": "lost", "reason": "refused"}
    assert (await client.post(f"{URL}/deals/{deal['id']}/close", json=body, headers=_h(head))).status_code == 200
    assert not await _assigned(db_session, x, student)


async def test_closing_one_deal_keeps_the_student_with_a_specialist_of_another(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User, head: User
) -> None:
    x = await _user(db_session, UserRole.psychologist, "Икс")
    student = await _user(db_session, UserRole.student)
    first, _ = await _booked_with(client, db_session, manager, x, time(10, 0))
    second, _ = await _booked_with(client, db_session, manager, x, time(12, 0))
    await _link(db_session, first, student)
    await _link(db_session, second, student)
    db_session.add(PsychologistStudentAssignment(psychologist_id=x.id, student_id=student.id))
    await db_session.flush()

    body = {"result": "lost", "reason": "refused"}
    assert (await client.post(f"{URL}/deals/{second['id']}/close", json=body, headers=_h(head))).status_code == 200
    assert await _assigned(db_session, x, student)
    status, _ = await _call_state(db_session, first["meeting"]["id"])
    assert status != MeetingStatus.cancelled


async def test_cancelling_the_later_deals_call_returns_the_student_to_the_earlier_specialist(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    _, new, _, _, student = await _two_deals(client, db_session, manager)
    path = f"{URL}/meetings/{new['meeting']['id']}/cancel"
    assert (await client.post(path, json={"reason": "Просьба клиента"}, headers=_h(manager))).status_code == 200
    assert await _holders(db_session, student) == ["Икс"]


async def test_a_call_on_an_earlier_deal_gives_its_specialist_the_student(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    x = await _user(db_session, UserRole.psychologist, "Икс")
    y = await _user(db_session, UserRole.psychologist, "Игрек")
    student = await _user(db_session, UserRole.student)
    latest, _ = await _booked_with(client, db_session, manager, x, time(9, 0))
    await _link(db_session, latest, student)
    earlier = await _ready_to_book(client, manager)
    await _link(db_session, earlier, student, days_ago=9)
    start = await _open_slots(db_session, y, FUTURE_DAY, time(12, 0), 1)

    body = {"start": _iso(start), "handoff": _handoff(), "specialist_id": str(y.id)}
    booked = await client.post(f"{URL}/deals/{earlier['id']}/booking", json=body, headers=_h(manager))
    assert booked.status_code == 200, booked.text
    assert await _holders(db_session, student) == ["Игрек", "Икс"]

