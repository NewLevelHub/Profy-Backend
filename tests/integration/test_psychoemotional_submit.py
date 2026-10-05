"""PRO-306 (two-phase): POST /assessment/{id}/psychoemotional/start stores
check-in + circle1 (before the main battery, §B4 п.1-2 — check-in comes
first), POST .../{run_id}/finish stores circle2 (at the end) on the same
append-only row. Validates §6.1, leaves metrics/flag for PRO-307/308."""
import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.psychoemotional_run import PsychoEmotionalRun
from app.models.user import User
from app.services import auth_service

_LIST1 = [4, 3, 2, 1, 5, 6, 0, 7]
_LIST2 = [3, 4, 2, 0, 1, 5, 6, 7]
_DT = [0, 2100, 1800, 2400, 3000, 1500, 1200, 900]
_CHECKIN = {"q1": "спокойно", "q2": "не указано", "q3": "хорошо"}
_START_PAYLOAD = {"list1": _LIST1, "list1_dt_ms": _DT, "checkin": _CHECKIN}
_FINISH_PAYLOAD = {"list2": _LIST2, "list2_dt_ms": _DT}


async def _auth(db: AsyncSession) -> tuple[User, Assessment, dict]:
    user = User(
        email=f"{uuid.uuid4()}@example.com", hashed_password="x",
        is_active=True, is_verified=True,
    )
    db.add(user)
    await db.flush()
    profile = Profile(
        user_id=user.id, name="Т", age=16, grade=10, city="Алматы",
        country="Казахстан", language="ru", age_group=AgeGroup.senior,
    )
    db.add(profile)
    await db.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()
    headers = {"Authorization": f"Bearer {auth_service.create_jwt_token(user.id)}"}
    return user, assessment, headers


async def _start(client: AsyncClient, assessment_id, headers, payload=None) -> str:
    resp = await client.post(
        f"/api/v1/assessment/{assessment_id}/psychoemotional/start",
        json=payload or _START_PAYLOAD, headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["run_id"]


async def test_start_stores_a_pending_run(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)

    run_id = await _start(client, assessment.id, headers)

    run = (await db_session.execute(
        select(PsychoEmotionalRun).where(PsychoEmotionalRun.id == uuid.UUID(run_id))
    )).scalar_one()
    assert run.list1 == _LIST1
    assert run.checkin == _CHECKIN
    assert run.list2 is None
    assert run.pause_actual_sec is None
    assert run.tech_invalid is False


async def test_finish_completes_the_same_row(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    run_id = await _start(client, assessment.id, headers)

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/psychoemotional/{run_id}/finish",
        json=_FINISH_PAYLOAD, headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"run_id": run_id, "tech_invalid": False}

    run = (await db_session.execute(
        select(PsychoEmotionalRun).where(PsychoEmotionalRun.id == uuid.UUID(run_id))
    )).scalar_one()
    assert run.list1 == _LIST1 and run.list2 == _LIST2
    assert run.checkin == _CHECKIN  # set on start, untouched by finish
    assert run.pause_actual_sec is not None and run.pause_actual_sec >= 0
    assert run.metrics == {}
    assert run.validity_flag is None  # PRO-307/308 fill this
    assert run.thresholds_version is None


async def test_repeat_start_returns_the_same_pending_run(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)

    first_id = await _start(client, assessment.id, headers)
    second_id = await _start(client, assessment.id, headers)

    rows = (await db_session.execute(
        select(PsychoEmotionalRun).where(
            PsychoEmotionalRun.assessment_id == assessment.id
        )
    )).scalars().all()
    assert first_id == second_id
    assert [str(row.id) for row in rows] == [first_id]


async def test_finish_retry_with_the_same_payload_is_idempotent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    run_id = await _start(client, assessment.id, headers)
    url = f"/api/v1/assessment/{assessment.id}/psychoemotional/{run_id}/finish"

    first = await client.post(url, json=_FINISH_PAYLOAD, headers=headers)
    assert first.status_code == 200

    second = await client.post(url, json=_FINISH_PAYLOAD, headers=headers)
    assert second.status_code == 200
    assert second.json() == first.json()


async def test_finish_retry_with_different_payload_is_409(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    run_id = await _start(client, assessment.id, headers)
    url = f"/api/v1/assessment/{assessment.id}/psychoemotional/{run_id}/finish"
    assert (await client.post(url, json=_FINISH_PAYLOAD, headers=headers)).status_code == 200

    changed = {
        "list2": list(reversed(_LIST2)),
        "list2_dt_ms": _DT,
    }
    response = await client.post(url, json=changed, headers=headers)
    assert response.status_code == 409


async def test_start_after_completion_appends_a_new_pending_run(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    first_id = await _start(client, assessment.id, headers)
    finish_url = f"/api/v1/assessment/{assessment.id}/psychoemotional/{first_id}/finish"
    assert (await client.post(finish_url, json=_FINISH_PAYLOAD, headers=headers)).status_code == 200

    second_id = await _start(client, assessment.id, headers)
    assert second_id != first_id
    rows = (await db_session.execute(
        select(PsychoEmotionalRun).where(
            PsychoEmotionalRun.assessment_id == assessment.id
        )
    )).scalars().all()
    assert len(rows) == 2


async def test_current_reports_not_started_pending_and_completed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    url = f"/api/v1/assessment/{assessment.id}/psychoemotional/current"

    response = await client.get(url, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"run_id": None, "status": "not_started"}

    run_id = await _start(client, assessment.id, headers)
    response = await client.get(url, headers=headers)
    assert response.json() == {"run_id": run_id, "status": "pending"}

    finish_url = f"/api/v1/assessment/{assessment.id}/psychoemotional/{run_id}/finish"
    assert (await client.post(finish_url, json=_FINISH_PAYLOAD, headers=headers)).status_code == 200
    response = await client.get(url, headers=headers)
    assert response.json() == {"run_id": run_id, "status": "completed"}


async def test_finish_unknown_run_is_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/psychoemotional/{uuid.uuid4()}/finish",
        json=_FINISH_PAYLOAD, headers=headers,
    )
    assert resp.status_code == 404


async def test_bad_permutation_on_start_marks_tech_invalid_but_still_stores(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    payload = {**_START_PAYLOAD, "list1": [0, 0, 1, 2, 3, 4, 5, 6]}  # dup 0, missing 7

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/psychoemotional/start",
        json=payload, headers=headers,
    )
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]

    run = (await db_session.execute(
        select(PsychoEmotionalRun).where(PsychoEmotionalRun.id == uuid.UUID(run_id))
    )).scalar_one()
    assert run.tech_invalid is True  # §6.1 — stored, not processed


async def test_bad_permutation_on_finish_marks_tech_invalid(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    run_id = await _start(client, assessment.id, headers)
    payload = {**_FINISH_PAYLOAD, "list2": [0, 0, 1, 2, 3, 4, 5, 6]}

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/psychoemotional/{run_id}/finish",
        json=payload, headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["tech_invalid"] is True


async def test_wrong_length_is_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    payload = {**_START_PAYLOAD, "list1": [1, 2, 3]}

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/psychoemotional/start",
        json=payload, headers=headers,
    )
    assert resp.status_code == 422


async def test_other_users_assessment_is_403_on_start(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, _ = await _auth(db_session)
    _, _, other_headers = await _auth(db_session)

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/psychoemotional/start",
        json=_START_PAYLOAD, headers=other_headers,
    )
    assert resp.status_code == 403


async def test_other_users_run_is_403_on_finish(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    run_id = await _start(client, assessment.id, headers)
    _, _, other_headers = await _auth(db_session)

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/psychoemotional/{run_id}/finish",
        json=_FINISH_PAYLOAD, headers=other_headers,
    )
    assert resp.status_code == 403
