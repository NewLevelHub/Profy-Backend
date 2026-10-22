"""The owner keeps the price list in the CRM (ТЗ §3.7): adds tariffs, changes
their terms, archives them. A deal keeps the price of the day it was picked."""

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.user import User, UserRole
from datetime import datetime, time

from tests.integration.test_crm_deals import (  # noqa: F401 — fixtures
    FUTURE_DAY,
    URL,
    _create,
    _h,
    _handoff,
    _iso,
    _ready_to_book,
    _user,
    head,
    manager,
)

BODY = {"name": "  Экспресс  ", "price": 25000, "meeting_minutes": 30, "description": "Короткая диагностика"}


@pytest.fixture
async def owner(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.owner, "Санжар")


async def _meta_tariff(client: httpx.AsyncClient, user: User, code: str) -> dict:
    meta = (await client.get(f"{URL}/meta", headers=_h(user))).json()
    return next(t for t in meta["tariffs"] if t["code"] == code)


async def test_owner_adds_and_changes_a_tariff(
    client: httpx.AsyncClient, db_session: AsyncSession, owner: User, manager: User
) -> None:
    created = await client.post(f"{URL}/tariffs", json=BODY, headers=_h(owner))
    assert created.status_code == 201, created.text
    tariff = created.json()
    assert tariff | {"code": None} == {
        "code": None, "name": "Экспресс", "price": 25000, "meeting_minutes": 30,
        "description": "Короткая диагностика", "psychologist_review": True, "active": True,
    }
    code = tariff["code"]
    assert await _meta_tariff(client, manager, code) == tariff

    # A deal fixes the price of the day.
    deal = await _create(client, manager)
    path = f"{URL}/deals/{deal['id']}"
    picked = await client.patch(path, json={"tariff_code": code}, headers=_h(manager))
    assert picked.json()["price"] == 25000

    changed = await client.patch(
        f"{URL}/tariffs/{code}", json={"price": 30000, "meeting_minutes": 60, "description": None}, headers=_h(owner)
    )
    assert changed.status_code == 200
    assert changed.json() | {"code": None} == {**tariff, "code": None, "price": 30000, "meeting_minutes": 60, "description": None}
    assert (await client.get(path, headers=_h(manager))).json()["price"] == 25000

    entries = (await db_session.execute(select(AuditLog).where(AuditLog.entity_id == code).order_by(AuditLog.at))).scalars().all()
    assert [e.action for e in entries] == ["crm.tariff_created", "crm.tariff_changed"]
    assert entries[1].before == {"price": 25000, "meeting_minutes": 30, "description": "Короткая диагностика"}


async def test_an_archived_tariff_stays_on_its_deals(
    client: httpx.AsyncClient, owner: User, manager: User
) -> None:
    code = (await client.post(f"{URL}/tariffs", json=BODY, headers=_h(owner))).json()["code"]
    deal = await _create(client, manager)
    path = f"{URL}/deals/{deal['id']}"
    assert (await client.patch(path, json={"tariff_code": code}, headers=_h(manager))).status_code == 200

    archived = await client.patch(f"{URL}/tariffs/{code}", json={"active": False}, headers=_h(owner))
    assert archived.json()["active"] is False
    assert (await _meta_tariff(client, manager, code))["active"] is False
    assert (await client.get(path, headers=_h(manager))).json()["tariff_code"] == code

    other = await _create(client, manager)
    refused = await client.patch(f"{URL}/deals/{other['id']}", json={"tariff_code": code}, headers=_h(manager))
    assert refused.json()["error_code"] == "tariff_not_found"


async def test_only_the_owner_edits_the_price_list(
    client: httpx.AsyncClient, owner: User, manager: User, head: User
) -> None:
    for user in (manager, head):
        assert (await client.post(f"{URL}/tariffs", json=BODY, headers=_h(user))).status_code == 403
        assert (await client.patch(f"{URL}/tariffs/testing", json={"price": 1}, headers=_h(user))).status_code == 403
    missing = await client.patch(f"{URL}/tariffs/nope", json={"price": 1}, headers=_h(owner))
    assert missing.json()["error_code"] == "tariff_not_found"
    for bad in ({**BODY, "name": "   "}, {**BODY, "price": -1}, {**BODY, "meeting_minutes": 45}):
        assert (await client.post(f"{URL}/tariffs", json=bad, headers=_h(owner))).status_code == 422


async def test_no_review_means_no_call(client: httpx.AsyncClient, owner: User, manager: User) -> None:
    """«Консультация и проверка отчёта психологом» comes with the call: a
    tariff without it has no call, and its deal is not booked."""
    plain = await client.post(f"{URL}/tariffs", json={**BODY, "psychologist_review": False}, headers=_h(owner))
    assert plain.status_code == 201 and plain.json()["meeting_minutes"] is None
    missing = await client.post(
        f"{URL}/tariffs", json={**BODY, "meeting_minutes": None, "psychologist_review": True}, headers=_h(owner)
    )
    assert missing.status_code == 422 and missing.json()["error_code"] == "tariff_meeting_required"

    reviewed = (await client.post(f"{URL}/tariffs", json=BODY, headers=_h(owner))).json()
    dropped = await client.patch(f"{URL}/tariffs/{reviewed['code']}", json={"psychologist_review": False}, headers=_h(owner))
    assert dropped.json()["meeting_minutes"] is None
    back = await client.patch(f"{URL}/tariffs/{reviewed['code']}", json={"psychologist_review": True}, headers=_h(owner))
    assert back.json()["error_code"] == "tariff_meeting_required"

    deal = await _ready_to_book(client, manager, tariff=plain.json()["code"])
    booked = await client.post(
        f"{URL}/deals/{deal['id']}/booking",
        json={"start": _iso(datetime.combine(FUTURE_DAY, time(10, 0))), "handoff": _handoff()},
        headers=_h(manager),
    )
    assert booked.status_code == 409 and booked.json()["error_code"] == "deal_no_meeting"
