"""Integration helpers for АСТУР attempts (PRO-427)."""
import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.astur_bank_version import AsturBankVersion
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import auth_service
from app.services.astur.bank import AsturBank
from tests.astur_fixtures import PROFILE_NAME, content_answers, expected_quick_answer, v1_bank


async def make_student(
    db: AsyncSession, *, age: int = 16, grade: int = 10, user: User | None = None
) -> tuple[User, Assessment, dict]:
    """A student with a fresh assessment; pass `user` to add another
    assessment for the same student."""
    if user is None:
        user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x", is_active=True, is_verified=True)
        db.add(user)
        await db.flush()
        profile = Profile(
            user_id=user.id, name=PROFILE_NAME, age=age, grade=grade, city="Алматы",
            country="Казахстан", language="ru", age_group=AgeGroup.senior,
        )
        db.add(profile)
        await db.flush()
    else:
        profile = (await db.execute(select(Profile).where(Profile.user_id == user.id))).scalar_one()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()
    return user, assessment, {"Authorization": f"Bearer {auth_service.create_jwt_token(user)}"}


async def v1_version_id(db: AsyncSession) -> uuid.UUID:
    return (await db.execute(select(AsturBankVersion.id).where(AsturBankVersion.version == 1))).scalar_one()


def answered(values: dict) -> dict:
    """{position: value} -> the explicit submit format."""
    return {k: {"status": "answered", "value": v} for k, v in values.items()}


def quick_payload(
    bank: AsturBank, run_id: uuid.UUID, *, elapsed_ms: int = 300, over_limit: set[int] = frozenset()
) -> dict:
    subtest = bank.subtest("lability")
    return {
        "run_id": str(run_id),
        "answers": answered({str(i): expected_quick_answer(item) for i, item in enumerate(subtest.items, start=1)}),
        "elapsed_ms": {
            str(i): (bank.lability_item_limit_ms + 1 if i in over_limit else elapsed_ms)
            for i in range(1, len(subtest.items) + 1)
        },
        "client_timezone": "Asia/Almaty",
    }


async def open_attempt(client: AsyncClient, assessment_id: uuid.UUID, headers: dict):
    resp = await client.post(f"/api/v1/assessment/{assessment_id}/astur/attempt", headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def submit(client: AsyncClient, assessment_id: uuid.UUID, number: int, payload: dict, headers: dict):
    return await client.post(f"/api/v1/assessment/{assessment_id}/astur/subtest/{number}", json=payload, headers=headers)


async def start(
    client: AsyncClient,
    assessment_id: uuid.UUID,
    number: int,
    run_id,
    headers: dict,
    *,
    state_version: int = 0,
):
    return await client.post(
        f"/api/v1/assessment/{assessment_id}/astur/subtest/{number}/start",
        json={"run_id": str(run_id), "state_version": state_version}, headers=headers,
    )


async def reset(
    client: AsyncClient,
    assessment_id: uuid.UUID,
    number: int,
    run_id,
    headers: dict,
    *,
    state_version: int = 0,
):
    return await client.post(
        f"/api/v1/assessment/{assessment_id}/astur/subtest/{number}/reset",
        json={"run_id": str(run_id), "state_version": state_version}, headers=headers,
    )


async def complete_attempt(
    client: AsyncClient,
    assessment_id: uuid.UUID,
    headers: dict,
    *,
    bank: AsturBank | None = None,
    wrong: set[str] = frozenset(),
    skip: set[str] = frozenset(),
) -> list:
    """Opens (or resumes) the attempt, then starts and submits every subtest
    in order (except `skip`); returns the submit responses. Subtests in
    `wrong` get valid-format but wrong answers."""
    bank = bank or v1_bank()
    run_id = (await open_attempt(client, assessment_id, headers))["run"]["run_id"]
    responses = []
    for subtest in sorted(bank.subtests, key=lambda s: s.number):
        if subtest.key in skip:
            continue
        started = await start(client, assessment_id, subtest.number, run_id, headers)
        assert started.status_code == 201, started.text
        if subtest.key == "lability":
            payload = quick_payload(bank, run_id)
        else:
            payload = {"run_id": run_id, "answers": answered(content_answers(bank, wrong=wrong)[subtest.key])}
        payload["started_at"] = started.json()["started_at"]
        resp = await submit(client, assessment_id, subtest.number, payload, headers)
        assert resp.status_code == 201, resp.text
        responses.append(resp)
    return responses
