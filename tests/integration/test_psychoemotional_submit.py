"""PRO-306: POST /assessment/{id}/psychoemotional stores one raw run
(append-only), validates §6.1, leaves metrics/flag for PRO-307/308."""
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
_PAYLOAD = {
    "list1": _LIST1,
    "list2": _LIST2,
    "list1_dt_ms": _DT,
    "list2_dt_ms": _DT,
    "pause_actual_sec": 130,
    "checkin": {"q1": "спокойно", "q2": "не указано", "q3": "хорошо"},
}


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


async def test_submit_stores_a_raw_run(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/psychoemotional",
        json=_PAYLOAD, headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["tech_invalid"] is False

    run = (await db_session.execute(
        select(PsychoEmotionalRun).where(
            PsychoEmotionalRun.assessment_id == assessment.id
        )
    )).scalar_one()
    assert run.list1 == _LIST1 and run.list2 == _LIST2
    assert run.pause_actual_sec == 130
    assert run.checkin["q2"] == "не указано"
    assert run.metrics == {}
    assert run.validity_flag is None  # PRO-307/308 fill this
    assert run.thresholds_version is None


async def test_repeat_submit_appends_a_second_row(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    url = f"/api/v1/assessment/{assessment.id}/psychoemotional"

    await client.post(url, json=_PAYLOAD, headers=headers)
    await client.post(url, json=_PAYLOAD, headers=headers)

    rows = (await db_session.execute(
        select(PsychoEmotionalRun).where(
            PsychoEmotionalRun.assessment_id == assessment.id
        )
    )).scalars().all()
    assert len(rows) == 2  # append-only, no overwrite


async def test_bad_permutation_marks_tech_invalid_but_still_stores(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    payload = {**_PAYLOAD, "list2": [0, 0, 1, 2, 3, 4, 5, 6]}  # dup 0, missing 7

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/psychoemotional",
        json=payload, headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["tech_invalid"] is True

    run = (await db_session.execute(
        select(PsychoEmotionalRun).where(
            PsychoEmotionalRun.assessment_id == assessment.id
        )
    )).scalar_one()
    assert run.tech_invalid is True  # §6.1 — stored, not processed


async def test_wrong_length_is_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    payload = {**_PAYLOAD, "list1": [1, 2, 3]}

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/psychoemotional",
        json=payload, headers=headers,
    )
    assert resp.status_code == 422


async def test_other_users_assessment_is_403(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, _ = await _auth(db_session)
    _, _, other_headers = await _auth(db_session)

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/psychoemotional",
        json=_PAYLOAD, headers=other_headers,
    )
    assert resp.status_code == 403
