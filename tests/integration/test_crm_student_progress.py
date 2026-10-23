"""The deal follows the student's account (ТЗ §3.3, §4.4): the invite link
ties the account, a finished test is stage 7, a published report is stage 8
and «Успешно». Without the link no student account can be made."""

import uuid
from datetime import time, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.analysis_result import AnalysisResult, ReviewStatus
from app.models.crm import CrmTask, TaskType
from app.models.psychologist_assignment import PsychologistStudentAssignment
from app.models.scheduling import Meeting
from app.models.user import User, UserRole
from app.services import email_service, tz
from app.services.oauth_service import google_id_token
from tests.integration.review_helpers import capture_emails, force_complete_senior, generate, make_student_assessment
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

ACCEPT = "/api/v1/student-invites/accept"


def _token(url: str) -> str:
    return url.split("#token=", 1)[1]


async def _booked(
    client: httpx.AsyncClient, db: AsyncSession, user: User, tariff: str = "testing", specialist: User | None = None
) -> dict:
    """A paid deal booked on a call — the link carries its specialist."""
    specialist = specialist or await _user(db, UserRole.psychologist, "Лолита")
    start = await _open_slots(db, specialist, FUTURE_DAY, time(10, 0), 2)
    deal = await _ready_to_book(client, user, tariff=tariff)
    booked = await client.post(
        f"{URL}/deals/{deal['id']}/booking", json={"start": _iso(start), "handoff": _handoff()}, headers=_h(user)
    )
    assert booked.status_code == 200, booked.text
    return booked.json()


async def _invite(client: httpx.AsyncClient, user: User, deal_id: str) -> str:
    response = await client.post(f"{URL}/deals/{deal_id}/invite", headers=_h(user))
    assert response.status_code == 200, response.text
    return response.json()["student_account"]["invite_url"]


async def test_invite_needs_payment_and_a_new_link_revokes_the_old(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User, test_user: User, auth_headers: dict[str, str]
) -> None:
    lead = await _create(client, manager)
    unpaid = await client.post(f"{URL}/deals/{lead['id']}/invite", headers=_h(manager))
    assert unpaid.json()["error_code"] == "deal_not_paid"

    # Paid, not booked yet: the link waits for the call and its specialist.
    paid = await _ready_to_book(client, manager)
    not_booked = await client.post(f"{URL}/deals/{paid['id']}/invite", headers=_h(manager))
    assert not_booked.json()["error_code"] == "deal_not_booked"

    deal = await _booked(client, db_session, manager)
    first = await _invite(client, manager, deal["id"])
    second = await _invite(client, manager, deal["id"])
    assert first != second and "/student-invite#token=" in second

    old = await client.post(ACCEPT, json={"token": _token(first)}, headers=auth_headers)
    assert old.status_code == 404 and old.json()["error_code"] == "student_invite_invalid"
    assert (await client.post(ACCEPT, json={"token": _token(second)}, headers=auth_headers)).status_code == 204
    # Opening it again changes nothing; another account cannot reuse it.
    assert (await client.post(ACCEPT, json={"token": _token(second)}, headers=auth_headers)).status_code == 204

    detail = (await client.get(f"{URL}/deals/{deal['id']}", headers=_h(manager))).json()
    assert detail["student_account"] == {
        "linked": True, "email": test_user.email, "invite_url": None, "invite_created_at": None,
    }
    assert detail["events"][0]["kind"] == "student_linked" and detail["events"][0]["actor"] is None


async def test_only_a_student_account_accepts(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User
) -> None:
    deal = await _booked(client, db_session, manager)
    url = await _invite(client, manager, deal["id"])
    response = await client.post(ACCEPT, json={"token": _token(url)}, headers=_h(manager))
    assert response.json()["error_code"] == "student_invite_students_only"
    assert (await client.post(ACCEPT, json={"token": _token(url)})).status_code == 401


async def test_owner_links_by_email_and_manager_cannot(
    client: httpx.AsyncClient, manager: User, head: User, test_user: User
) -> None:
    deal = await _ready_to_book(client, manager)
    path = f"{URL}/deals/{deal['id']}/student"
    assert (await client.post(path, json={"email": test_user.email}, headers=_h(manager))).status_code == 403
    missing = await client.post(path, json={"email": "nobody@example.test"}, headers=_h(head))
    assert missing.json()["error_code"] == "student_account_not_found"
    linked = await client.post(path, json={"email": test_user.email.upper()}, headers=_h(head))
    assert linked.status_code == 200 and linked.json()["student_account"]["linked"] is True


async def test_test_and_report_move_the_deal(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    manager: User,
    test_user: User,
    auth_headers: dict[str, str],
    psychologist_user: User,
    psychologist_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    start = await _open_slots(db_session, psychologist_user, FUTURE_DAY, time(10, 0), 1)
    deal = await _ready_to_book(client, manager)
    booked = await client.post(
        f"{URL}/deals/{deal['id']}/booking", json={"start": _iso(start), "handoff": _handoff()}, headers=_h(manager)
    )
    assert booked.status_code == 200, booked.text
    url = await _invite(client, manager, deal["id"])
    assert (await client.post(ACCEPT, json={"token": _token(url)}, headers=auth_headers)).status_code == 204

    # The specialist of the booked call gets the student.
    assert await db_session.scalar(
        select(PsychologistStudentAssignment.id).where(
            PsychologistStudentAssignment.psychologist_id == psychologist_user.id,
            PsychologistStudentAssignment.student_id == test_user.id,
        )
    )

    assessment = await make_student_assessment(db_session, test_user)
    assert (await generate(client, auth_headers, assessment)).status_code == 200
    detail = (await client.get(f"{URL}/deals/{deal['id']}", headers=_h(manager))).json()
    assert detail["stage"] == "diagnostics_done" and detail["result"] == "open"
    assert detail["events"][0]["data"] == {"from": "paid", "to": "diagnostics_done", "auto": True}

    published = await client.post(
        f"/api/v1/psychologist/students/{test_user.id}/results/{assessment.id}/publish", headers=psychologist_headers
    )
    assert published.status_code == 200, published.text
    detail = (await client.get(f"{URL}/deals/{deal['id']}", headers=_h(manager))).json()
    assert detail["stage"] == "report_published" and detail["result"] == "won"
    assert [e["kind"] for e in detail["events"][:2]] == ["closed", "stage"]


async def test_linking_late_catches_up_and_unpaid_gets_a_task(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    manager: User,
    head: User,
    test_user: User,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    lead = await _create(client, manager)
    path = f"{URL}/deals/{lead['id']}"
    assert (await client.patch(path, json={"is_target": True, "tariff_code": "testing"}, headers=_h(manager))).status_code == 200
    assessment = await make_student_assessment(db_session, test_user)
    assert (await generate(client, auth_headers, assessment)).status_code == 200

    # Linked after the test: an unpaid deal stays put, its manager checks the payment.
    linked = await client.post(f"{path}/student", json={"email": test_user.email}, headers=_h(head))
    assert linked.json()["stage"] == "qualification"
    tasks = (await db_session.execute(select(CrmTask).where(CrmTask.deal_id == lead["id"]))).scalars().all()
    assert [(t.type, t.assignee_id) for t in tasks] == [(TaskType.payment_check, manager.id)]

    paid = await client.post(f"{path}/payment", json={"amount": 45000, "method": "transfer"}, headers=_h(manager))
    assert paid.json()["stage"] == "paid"
    # Paid now — the next sync (here: linking again) catches up.
    relinked = await client.post(f"{path}/student", json={"email": test_user.email}, headers=_h(head))
    assert relinked.json()["stage"] == "diagnostics_done"
    assert len((await db_session.execute(select(CrmTask).where(CrmTask.deal_id == lead["id"]))).scalars().all()) == 1


async def test_a_lost_deal_does_not_move(
    client: httpx.AsyncClient, db_session: AsyncSession, head: User, test_user: User
) -> None:
    deal = await _ready_to_book(client, head)
    closed = await client.post(f"{URL}/deals/{deal['id']}/close", json={"result": "lost", "reason": "refund"}, headers=_h(head))
    assert closed.status_code == 200
    linked = await client.post(f"{URL}/deals/{deal['id']}/student", json={"email": test_user.email}, headers=_h(head))
    assert linked.json()["error_code"] == "deal_closed"
    assert test_user.role == UserRole.student


# ── registration is invite-only ─────────────────────────────────────────────


@pytest.fixture
def invite_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "REGISTRATION_INVITE_ONLY", True)
    monkeypatch.setattr(email_service, "send_verification_email", AsyncMock())


async def test_sign_up_needs_a_live_invite(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User, invite_only: None
) -> None:
    body = {"email": f"{uuid.uuid4().hex}@gmail.com", "password": "Testpass123!"}
    closed = await client.post("/api/v1/auth/register", json=body)
    assert closed.status_code == 403 and closed.json()["error_code"] == "registration_invite_only"
    fake = await client.post("/api/v1/auth/register", json={**body, "student_invite": "x" * 43})
    assert fake.json()["error_code"] == "registration_invite_only"

    deal = await _booked(client, db_session, manager)
    token = _token(await _invite(client, manager, deal["id"]))
    assert (await client.post("/api/v1/auth/register", json={**body, "student_invite": token})).status_code == 201


async def test_google_sign_up_needs_an_invite_but_sign_in_does_not(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    manager: User,
    test_user: User,
    invite_only: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claims = {"sub": str(uuid.uuid4()), "email": f"{uuid.uuid4().hex}@gmail.com", "email_verified": True}
    monkeypatch.setattr(google_id_token, "verify_oauth2_token", lambda *a, **kw: claims)
    closed = await client.post("/api/v1/auth/google", json={"id_token": "t"})
    assert closed.status_code == 403 and closed.json()["error_code"] == "registration_invite_only"

    deal = await _booked(client, db_session, manager)
    token = _token(await _invite(client, manager, deal["id"]))
    created = await client.post("/api/v1/auth/google", json={"id_token": "t", "student_invite": token})
    assert created.status_code == 200 and created.json()["user"]["role"] == "student"

    # An existing account signs in with Google as before.
    claims.update(sub=str(uuid.uuid4()), email=test_user.email)
    assert (await client.post("/api/v1/auth/google", json={"id_token": "t"})).status_code == 200


# ── the tariff decides whether a psychologist reviews the report ────────────


async def _tariff(client: httpx.AsyncClient, db_session: AsyncSession, *, review: bool) -> str:
    owner = await _user(db_session, UserRole.owner, "Санжар")
    body = {"name": "Экспресс", "price": 25000, "meeting_minutes": 30, "psychologist_review": review}
    created = await client.post(f"{URL}/tariffs", json=body, headers=_h(owner))
    assert created.status_code == 201 and created.json()["psychologist_review"] is review
    return created.json()["code"]


async def _status(db_session: AsyncSession, assessment_id) -> ReviewStatus:
    return await db_session.scalar(
        select(AnalysisResult.review_status).where(AnalysisResult.assessment_id == assessment_id)
    )


async def test_a_tariff_without_review_publishes_the_report_at_once(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    manager: User,
    test_user: User,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    code = await _tariff(client, db_session, review=False)
    deal = await _ready_to_book(client, manager, tariff=code)
    assert deal["psychologist_review"] is False
    url = await _invite(client, manager, deal["id"])
    assert (await client.post(ACCEPT, json={"token": _token(url)}, headers=auth_headers)).status_code == 204

    assessment = await make_student_assessment(db_session, test_user)
    assessment_id = assessment.id
    generated = await generate(client, auth_headers, assessment)
    assert generated.status_code == 200, generated.text
    assert await _status(db_session, assessment_id) == ReviewStatus.published
    detail = (await client.get(f"{URL}/deals/{deal['id']}", headers=_h(manager))).json()
    assert detail["stage"] == "report_published" and detail["result"] == "won"
    # The student is told; no psychologist is asked to review.
    assert sent["published"].await_count == 1 and sent["pending"].await_count == 0


async def test_review_stays_with_the_tariff_and_without_payment(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    manager: User,
    test_user: User,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    code = await _tariff(client, db_session, review=False)
    # Picked, then not paid: the report waits for a psychologist.
    lead = await _create(client, manager)
    path = f"{URL}/deals/{lead['id']}"
    assert (await client.patch(path, json={"is_target": True, "tariff_code": code}, headers=_h(manager))).status_code == 200
    head_user = await _user(db_session, UserRole.sales_head, "РОП")
    assert (await client.post(f"{path}/student", json={"email": test_user.email}, headers=_h(head_user))).status_code == 200

    assessment = await make_student_assessment(db_session, test_user)
    assessment_id = assessment.id
    assert (await generate(client, auth_headers, assessment)).status_code == 200
    assert await _status(db_session, assessment_id) == ReviewStatus.pending_review


async def test_a_reviewed_tariff_keeps_the_review_after_the_owner_drops_it(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    manager: User,
    test_user: User,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    code = await _tariff(client, db_session, review=True)
    deal = await _booked(client, db_session, manager, tariff=code)
    owner = await _user(db_session, UserRole.owner, "Санжар")
    # The condition the deal was sold with stays, like its price.
    assert (await client.patch(f"{URL}/tariffs/{code}", json={"psychologist_review": False}, headers=_h(owner))).status_code == 200
    url = await _invite(client, manager, deal["id"])
    assert (await client.post(ACCEPT, json={"token": _token(url)}, headers=auth_headers)).status_code == 204

    assessment = await make_student_assessment(db_session, test_user)
    assessment_id = assessment.id
    assert (await generate(client, auth_headers, assessment)).status_code == 200
    assert await _status(db_session, assessment_id) == ReviewStatus.pending_review


# ── the second call, set by the specialist (ТЗ §4.5) ────────────────────────


async def test_the_specialist_sets_the_second_call_and_the_deal_follows(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    manager: User,
    test_user: User,
    auth_headers: dict[str, str],
    psychologist_user: User,
    psychologist_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    deal = await _booked(client, db_session, manager, specialist=psychologist_user)
    url = await _invite(client, manager, deal["id"])
    assert (await client.post(ACCEPT, json={"token": _token(url)}, headers=auth_headers)).status_code == 204
    path = f"/api/v1/psychologist/students/{test_user.id}/second-meeting"

    # Before the first call has begun there is nothing to set.
    before = (await client.get(path, headers=psychologist_headers)).json()
    assert before["first"] is not None and before["second"] is None
    assert before["can_schedule"] is False and before["blocker"] == "first_not_started"

    first = await db_session.get(Meeting, uuid.UUID(before["first"]["id"]))
    first.start_at, first.end_at = tz.now_utc() - timedelta(hours=1), tz.now_utc() - timedelta(minutes=30)
    await db_session.flush()

    # Any time without an overlap; the time is taken in the schedule.
    second_start = await _open_slots(db_session, psychologist_user, FUTURE_DAY, time(15, 0), 2)
    misaligned = await client.post(path, json={"start": _iso(second_start + timedelta(minutes=10))}, headers=psychologist_headers)
    assert misaligned.status_code == 422
    set_ = await client.post(path, json={"start": _iso(second_start)}, headers=psychologist_headers)
    assert set_.status_code == 200, set_.text
    state = set_.json()
    assert state["second"]["start"].startswith(second_start.strftime("%Y-%m-%dT%H:%M")) and state["blocker"] == "already_scheduled"
    again = await client.post(path, json={"start": _iso(second_start + timedelta(hours=2))}, headers=psychologist_headers)
    assert again.json()["error_code"] == "second_meeting_already_scheduled"

    # The CRM cannot book that time any more.
    other = await _ready_to_book(client, manager)
    taken = await client.post(
        f"{URL}/deals/{other['id']}/booking", json={"start": _iso(second_start), "handoff": _handoff()}, headers=_h(manager)
    )
    assert taken.json()["error_code"] == "slot_taken"

    detail = (await client.get(f"{URL}/deals/{deal['id']}", headers=_h(manager))).json()
    assert [m["start"][:16] for m in detail["meetings"]] == [
        first.start_at.isoformat()[:16], state["second"]["start"][:16],
    ]
    assert detail["meeting"]["id"] == before["first"]["id"]

    # The test, then the report published on the second call: «Успешно» and
    # «Разбор назначен»; the call held — «Разбор проведён».
    assessment = await make_student_assessment(db_session, test_user)
    assert (await generate(client, auth_headers, assessment)).status_code == 200
    published = await client.post(
        f"/api/v1/psychologist/students/{test_user.id}/results/{assessment.id}/publish", headers=psychologist_headers
    )
    assert published.status_code == 200, published.text
    detail = (await client.get(f"{URL}/deals/{deal['id']}", headers=_h(manager))).json()
    assert detail["stage"] == "review_scheduled" and detail["result"] == "won"

    second = await db_session.get(Meeting, uuid.UUID(state["second"]["id"]))
    second.start_at = tz.now_utc() - timedelta(minutes=5)
    await db_session.flush()
    done = await client.post(
        f"/api/v1/scheduling/specialists/me/meetings/{second.id}/status", json={"status": "done"}, headers=psychologist_headers
    )
    assert done.status_code == 200, done.text
    detail = (await client.get(f"{URL}/deals/{deal['id']}", headers=_h(manager))).json()
    assert detail["stage"] == "review_done" and detail["result"] == "won"


async def test_only_the_students_own_specialist_sets_the_second_call(
    client: httpx.AsyncClient, db_session: AsyncSession, manager: User, test_user: User, psychologist_headers: dict[str, str]
) -> None:
    other = await _user(db_session, UserRole.psychologist, "Азат")
    await _booked(client, db_session, manager, specialist=other)
    path = f"/api/v1/psychologist/students/{test_user.id}/second-meeting"
    assert (await client.get(path, headers=psychologist_headers)).status_code == 404
