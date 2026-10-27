"""Specialist schedule API (PRO-513/514) against
docs/frontend-scheduling-api-contract.md."""

import uuid
from datetime import date, datetime, time, timedelta

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.user import User, UserRole
from app.services import auth_service, tz

URL = "/api/v1/scheduling"


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


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_service.create_jwt_token(user)}"}


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _future_monday() -> date:
    """A Monday whose whole week is outside the freeze."""
    return tz.week_start(tz.today() + timedelta(days=14))


def _interval(day: date, start: time, end: time, state: str = "free") -> dict:
    return {"start": _iso(tz.at(day, start)), "end": _iso(tz.at(day, end)), "state": state}


def _slot(week: dict, moment: datetime) -> dict:
    for day in week["days"]:
        for slot in day["slots"]:
            if slot["start"] == _iso(moment):
                return slot
    raise AssertionError(f"no slot {moment}")


@pytest.fixture
async def specialist(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.psychologist, "Азат Сейткали")


@pytest.fixture
async def owner(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.owner, "Санжар")


# ── access ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", [UserRole.student, UserRole.admin, UserRole.marketer])
async def test_roles_without_schedule_access_get_403(
    client: httpx.AsyncClient, db_session: AsyncSession, role: UserRole
) -> None:
    user = await _user(db_session, role)
    for path in ("/config", "/specialists", f"/specialists/me/weeks/{_future_monday()}",
                 f"/free?from={tz.today()}&to={tz.today()}"):
        response = await client.get(URL + path, headers=_headers(user))
        assert response.status_code == 403, path


async def test_config_follows_almaty_calendar(
    client: httpx.AsyncClient, specialist: User
) -> None:
    response = await client.get(URL + "/config", headers=_headers(specialist))
    assert response.status_code == 200
    body = response.json()
    assert body["timezone"] == "Asia/Almaty"
    assert body["slot_minutes"] == 30
    assert body["freeze_days"] == 3
    assert date.fromisoformat(body["editable_from"]) == tz.today() + timedelta(days=3)


async def test_specialist_cannot_read_someone_elses_schedule(
    client: httpx.AsyncClient, db_session: AsyncSession, specialist: User
) -> None:
    other = await _user(db_session, UserRole.psychologist)
    response = await client.get(
        f"{URL}/specialists/{other.id}/weeks/{_future_monday()}", headers=_headers(specialist)
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "specialist_not_found"


# ── week ────────────────────────────────────────────────────────────────────


async def test_new_week_is_all_closed_grid(client: httpx.AsyncClient, specialist: User) -> None:
    monday = _future_monday()
    response = await client.get(f"{URL}/specialists/me/weeks/{monday}", headers=_headers(specialist))
    assert response.status_code == 200
    week = response.json()
    assert week["specialist"]["full_name"] == "Азат Сейткали"
    assert week["published"] is False
    assert len(week["days"]) == 7
    assert all(len(day["slots"]) == 28 for day in week["days"])
    assert {slot["state"] for day in week["days"] for slot in day["slots"]} == {"closed"}
    assert week["days"][0]["slots"][0]["start"] == _iso(tz.at(monday, time(8, 0)))


async def test_week_start_must_be_monday(client: httpx.AsyncClient, specialist: User) -> None:
    tuesday = _future_monday() + timedelta(days=1)
    response = await client.get(f"{URL}/specialists/me/weeks/{tuesday}", headers=_headers(specialist))
    assert response.status_code == 422
    assert response.json()["error_code"] == "week_start_not_monday"


# ── availability ────────────────────────────────────────────────────────────


async def test_specialist_opens_slots_and_change_is_journaled(
    client: httpx.AsyncClient, db_session: AsyncSession, specialist: User
) -> None:
    day = _future_monday() + timedelta(days=2)
    response = await client.patch(
        f"{URL}/specialists/me/availability",
        json={"changes": [
            _interval(day, time(10, 0), time(11, 0)),
            _interval(day, time(14, 0), time(14, 30), "personal"),
        ]},
        headers=_headers(specialist),
    )
    assert response.status_code == 200, response.text
    week = response.json()["weeks"][0]
    assert _slot(week, tz.at(day, time(10, 0)))["state"] == "free"
    assert _slot(week, tz.at(day, time(10, 30)))["state"] == "free"
    assert _slot(week, tz.at(day, time(11, 0)))["state"] == "closed"
    assert _slot(week, tz.at(day, time(14, 0)))["state"] == "personal"

    entry = await db_session.scalar(
        select(AuditLog).where(AuditLog.entity_id == str(specialist.id))
    )
    assert entry.action == "schedule.availability_changed"
    assert entry.actor_role == "psychologist"
    assert entry.after[_iso(tz.at(day, time(10, 0)))] == "free"
    assert entry.before[_iso(tz.at(day, time(10, 0)))] == "closed"

    # Closing again removes the slot.
    closed = await client.patch(
        f"{URL}/specialists/me/availability",
        json={"changes": [_interval(day, time(10, 0), time(10, 30), "closed")]},
        headers=_headers(specialist),
    )
    assert _slot(closed.json()["weeks"][0], tz.at(day, time(10, 0)))["state"] == "closed"


async def test_specialist_cannot_change_frozen_days(
    client: httpx.AsyncClient, specialist: User
) -> None:
    tomorrow = tz.today() + timedelta(days=1)
    response = await client.patch(
        f"{URL}/specialists/me/availability",
        json={"changes": [_interval(tomorrow, time(20, 0), time(21, 0))]},
        headers=_headers(specialist),
    )
    assert response.status_code == 409
    body = response.json()
    assert body["error_code"] == "slot_frozen"
    assert [c["start"] for c in body["conflicts"]] == [
        _iso(tz.at(tomorrow, time(20, 0))), _iso(tz.at(tomorrow, time(20, 30)))
    ]


async def test_third_day_is_editable(client: httpx.AsyncClient, specialist: User) -> None:
    day = tz.today() + timedelta(days=3)
    response = await client.patch(
        f"{URL}/specialists/me/availability",
        json={"changes": [_interval(day, time(10, 0), time(10, 30))]},
        headers=_headers(specialist),
    )
    assert response.status_code == 200, response.text


async def test_past_time_cannot_be_changed(client: httpx.AsyncClient, owner: User, specialist: User) -> None:
    yesterday = tz.today() - timedelta(days=1)
    response = await client.patch(
        f"{URL}/specialists/{specialist.id}/availability",
        json={"changes": [_interval(yesterday, time(10, 0), time(10, 30))], "reason": "проверка"},
        headers=_headers(owner),
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "slot_in_past"


async def test_batch_is_all_or_nothing(client: httpx.AsyncClient, specialist: User) -> None:
    day = _future_monday()
    tomorrow = tz.today() + timedelta(days=1)
    response = await client.patch(
        f"{URL}/specialists/me/availability",
        json={"changes": [
            _interval(day, time(10, 0), time(10, 30)),
            _interval(tomorrow, time(21, 0), time(21, 30)),
        ]},
        headers=_headers(specialist),
    )
    assert response.status_code == 409
    week = (await client.get(f"{URL}/specialists/me/weeks/{day}", headers=_headers(specialist))).json()
    assert _slot(week, tz.at(day, time(10, 0)))["state"] == "closed"


@pytest.mark.parametrize(
    ("start", "end", "code"),
    [
        (time(10, 15), time(11, 0), "slot_misaligned"),
        (time(11, 0), time(10, 0), "slot_misaligned"),
        (time(7, 30), time(8, 30), "slot_out_of_grid"),
    ],
)
async def test_interval_must_fit_the_grid(
    client: httpx.AsyncClient, specialist: User, start: time, end: time, code: str
) -> None:
    response = await client.patch(
        f"{URL}/specialists/me/availability",
        json={"changes": [_interval(_future_monday(), start, end)]},
        headers=_headers(specialist),
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == code


async def test_overlapping_changes_are_rejected(client: httpx.AsyncClient, specialist: User) -> None:
    day = _future_monday()
    response = await client.patch(
        f"{URL}/specialists/me/availability",
        json={"changes": [
            _interval(day, time(10, 0), time(11, 0)),
            _interval(day, time(10, 30), time(11, 30), "personal"),
        ]},
        headers=_headers(specialist),
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "changes_overlap"


async def test_owner_changes_frozen_day_only_with_reason(
    client: httpx.AsyncClient, db_session: AsyncSession, owner: User, specialist: User
) -> None:
    tomorrow = tz.today() + timedelta(days=1)
    path = f"{URL}/specialists/{specialist.id}/availability"
    change = {"changes": [_interval(tomorrow, time(21, 0), time(21, 30))]}

    no_reason = await client.patch(path, json=change, headers=_headers(owner))
    assert no_reason.status_code == 422
    assert no_reason.json()["error_code"] == "reason_required"

    ok = await client.patch(path, json={**change, "reason": "болезнь специалиста"}, headers=_headers(owner))
    assert ok.status_code == 200, ok.text
    entry = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(specialist.id)))
    assert entry.actor_role == "owner"
    assert entry.reason == "болезнь специалиста"


async def test_owner_has_no_own_schedule(client: httpx.AsyncClient, owner: User) -> None:
    response = await client.get(f"{URL}/specialists/me/weeks/{_future_monday()}", headers=_headers(owner))
    assert response.status_code == 404


# ── copy, template, publish ─────────────────────────────────────────────────


async def test_copy_previous_week(client: httpx.AsyncClient, specialist: User) -> None:
    source = _future_monday()
    target = source + timedelta(days=7)
    await client.patch(
        f"{URL}/specialists/me/availability",
        json={"changes": [_interval(source + timedelta(days=1), time(13, 0), time(14, 0))]},
        headers=_headers(specialist),
    )
    response = await client.post(
        f"{URL}/specialists/me/weeks/{target}/copy-previous", json={}, headers=_headers(specialist)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["skipped"] == []
    copied = tz.at(target + timedelta(days=1), time(13, 30))
    assert _slot(body["week"], copied)["state"] == "free"


async def test_template_roundtrip_and_apply(client: httpx.AsyncClient, specialist: User) -> None:
    empty = await client.post(
        f"{URL}/specialists/me/weeks/{_future_monday()}/apply-template", json={}, headers=_headers(specialist)
    )
    assert empty.status_code == 409
    assert empty.json()["error_code"] == "template_empty"

    template = {"days": {"3": [{"start": "10:00", "end": "12:00", "state": "free"}]}}
    saved = await client.put(f"{URL}/specialists/me/template", json=template, headers=_headers(specialist))
    assert saved.status_code == 200, saved.text
    assert saved.json()["days"]["3"][0]["start"] == "10:00"
    assert saved.json()["days"]["1"] == []

    monday = _future_monday()
    applied = await client.post(
        f"{URL}/specialists/me/weeks/{monday}/apply-template", json={}, headers=_headers(specialist)
    )
    assert applied.status_code == 200, applied.text
    wednesday = monday + timedelta(days=2)
    assert _slot(applied.json()["week"], tz.at(wednesday, time(11, 30)))["state"] == "free"
    assert _slot(applied.json()["week"], tz.at(wednesday, time(12, 0)))["state"] == "closed"


async def test_template_skips_frozen_days(client: httpx.AsyncClient, specialist: User) -> None:
    template = {"days": {str(n): [{"start": "08:00", "end": "22:00", "state": "free"}] for n in range(1, 8)}}
    await client.put(f"{URL}/specialists/me/template", json=template, headers=_headers(specialist))
    # The week of tomorrow: tomorrow is frozen and still in the future.
    frozen_week = tz.week_start(tz.today() + timedelta(days=1))
    response = await client.post(
        f"{URL}/specialists/me/weeks/{frozen_week}/apply-template", json={}, headers=_headers(specialist)
    )
    assert response.status_code == 200
    skipped_codes = {item["error_code"] for item in response.json()["skipped"]}
    assert "slot_frozen" in skipped_codes
    for day in response.json()["week"]["days"]:
        if day["frozen"]:
            assert all(slot["state"] == "closed" for slot in day["slots"])


async def test_publish_is_idempotent_and_listed(
    client: httpx.AsyncClient, owner: User, specialist: User
) -> None:
    monday = _future_monday()
    first = await client.post(f"{URL}/specialists/me/weeks/{monday}/publish", headers=_headers(specialist))
    assert first.status_code == 200
    assert first.json()["published"] is True
    again = await client.post(f"{URL}/specialists/me/weeks/{monday}/publish", headers=_headers(specialist))
    assert again.json()["published_at"] == first.json()["published_at"]

    listed = await client.get(f"{URL}/specialists?week_start={monday}", headers=_headers(owner))
    assert listed.status_code == 200
    item = next(i for i in listed.json()["items"] if i["id"] == str(specialist.id))
    assert item["week_published"] is True


# ── free time ───────────────────────────────────────────────────────────────


async def test_free_time_hides_names_from_sales_manager(
    client: httpx.AsyncClient, db_session: AsyncSession, owner: User, specialist: User
) -> None:
    manager = await _user(db_session, UserRole.sales_manager)
    sales_head = await _user(db_session, UserRole.sales_head)
    day = _future_monday()
    await client.patch(
        f"{URL}/specialists/me/availability",
        json={"changes": [_interval(day, time(10, 0), time(11, 0))]},
        headers=_headers(specialist),
    )
    query = f"{URL}/free?from={day}&to={day}&duration=30"

    as_manager = await client.get(query, headers=_headers(manager))
    assert as_manager.status_code == 200
    assert "specialists" not in as_manager.text
    assert str(specialist.id) not in as_manager.text
    mine = [s for s in as_manager.json()["slots"] if s["start"] == _iso(tz.at(day, time(10, 0)))]
    assert mine and mine[0]["free_count"] >= 1

    for viewer in (owner, sales_head):
        named = await client.get(query, headers=_headers(viewer))
        slot = next(s for s in named.json()["slots"] if s["start"] == _iso(tz.at(day, time(10, 0))))
        assert {"id": str(specialist.id), "full_name": "Азат Сейткали"} in slot["specialists"]

    filtered = await client.get(query + f"&specialist_id={specialist.id}", headers=_headers(manager))
    assert filtered.status_code == 403


async def test_free_60_needs_two_adjacent_slots_of_one_specialist(
    client: httpx.AsyncClient, db_session: AsyncSession, owner: User, specialist: User
) -> None:
    other = await _user(db_session, UserRole.psychologist, "Лолита")
    day = _future_monday() + timedelta(days=3)
    await client.patch(
        f"{URL}/specialists/me/availability",
        json={"changes": [_interval(day, time(9, 0), time(9, 30)), _interval(day, time(15, 0), time(16, 0))]},
        headers=_headers(specialist),
    )
    await client.patch(
        f"{URL}/specialists/me/availability",
        json={"changes": [_interval(day, time(9, 30), time(10, 0))]},
        headers=_headers(other),
    )
    response = await client.get(
        f"{URL}/free?from={day}&to={day}&duration=60&specialist_id={specialist.id}", headers=_headers(owner)
    )
    starts = [s["start"] for s in response.json()["slots"]]
    # 09:00 + 09:30 belong to different specialists — not a 60-minute window.
    assert starts == [_iso(tz.at(day, time(15, 0)))]
    assert response.json()["slots"][0]["end"] == _iso(tz.at(day, time(16, 0)))


@pytest.mark.parametrize(
    ("to_offset", "duration", "code"),
    [
        (0, 45, "duration_invalid"),
        (-1, 30, "range_invalid"),
        (42, 30, "range_invalid"),
    ],
    ids=["duration", "to_before_from", "longer_than_42_days"],
)
async def test_free_validates_query(
    client: httpx.AsyncClient, owner: User, to_offset: int, duration: int, code: str
) -> None:
    start = tz.today()
    end = start + timedelta(days=to_offset)
    response = await client.get(
        f"{URL}/free?from={start}&to={end}&duration={duration}", headers=_headers(owner)
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == code


# ── settings ────────────────────────────────────────────────────────────────


async def test_settings_owner_only(
    client: httpx.AsyncClient, owner: User, specialist: User
) -> None:
    assert (await client.get(f"{URL}/settings", headers=_headers(specialist))).status_code == 403
    current = await client.get(f"{URL}/settings", headers=_headers(owner))
    assert current.status_code == 200
    updated = await client.put(
        f"{URL}/settings",
        json={"week_reminder_weekday": 4, "week_reminder_time": "17:30"},
        headers=_headers(owner),
    )
    assert updated.status_code == 200
    assert updated.json() == {"week_reminder_weekday": 4, "week_reminder_time": "17:30"}
    misaligned = await client.put(
        f"{URL}/settings",
        json={"week_reminder_weekday": 4, "week_reminder_time": "17:15"},
        headers=_headers(owner),
    )
    assert misaligned.status_code == 422


# ── journal ─────────────────────────────────────────────────────────────────


async def test_audit_log_rejects_update_and_delete(db_session: AsyncSession, owner: User) -> None:
    entry = AuditLog(actor_id=owner.id, actor_role="owner", action="test", entity_type="t", entity_id="1")
    db_session.add(entry)
    await db_session.flush()
    for statement in (
        text("UPDATE audit_log SET action = 'x' WHERE id = :id"),
        text("DELETE FROM audit_log WHERE id = :id"),
    ):
        savepoint = await db_session.begin_nested()
        with pytest.raises(DBAPIError, match="append-only"):
            await db_session.execute(statement, {"id": entry.id})
        await savepoint.rollback()


async def test_deleting_actor_keeps_journal_entry(db_session: AsyncSession) -> None:
    actor = await _user(db_session, UserRole.owner)
    entry = AuditLog(actor_id=actor.id, actor_role="owner", action="test", entity_type="t", entity_id="1")
    db_session.add(entry)
    await db_session.flush()
    await db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": actor.id})
    await db_session.refresh(entry)
    assert entry.actor_id is None
    assert entry.actor_role == "owner"
