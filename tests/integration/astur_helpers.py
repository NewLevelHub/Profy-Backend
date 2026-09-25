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


async def make_student(db: AsyncSession, *, age: int = 16, grade: int = 10) -> tuple[User, Assessment, dict]:
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x", is_active=True, is_verified=True)
    db.add(user)
    await db.flush()
    profile = Profile(
        user_id=user.id, name=PROFILE_NAME, age=age, grade=grade, city="Алматы",
        country="Казахстан", language="ru", age_group=AgeGroup.senior,
    )
    db.add(profile)
    await db.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()
    return user, assessment, {"Authorization": f"Bearer {auth_service.create_jwt_token(user.id)}"}


async def v1_version_id(db: AsyncSession) -> uuid.UUID:
    return (await db.execute(select(AsturBankVersion.id).where(AsturBankVersion.version == 1))).scalar_one()


def quick_payload(bank: AsturBank, *, elapsed_ms: int = 1500, over_limit: set[int] = frozenset()) -> dict:
    subtest = bank.subtest("lability")
    return {
        "answers": {str(i): expected_quick_answer(item) for i, item in enumerate(subtest.items, start=1)},
        "elapsed_ms": {
            str(i): (bank.lability_item_limit_ms + 1 if i in over_limit else elapsed_ms)
            for i in range(1, len(subtest.items) + 1)
        },
        "client_timezone": "Asia/Almaty",
    }


async def submit(client: AsyncClient, assessment_id: uuid.UUID, number: int, payload: dict, headers: dict):
    return await client.post(f"/api/v1/assessment/{assessment_id}/astur/subtest/{number}", json=payload, headers=headers)


async def complete_attempt(
    client: AsyncClient,
    assessment_id: uuid.UUID,
    headers: dict,
    *,
    bank: AsturBank | None = None,
    wrong: set[str] = frozenset(),
    skip: set[str] = frozenset(),
) -> list:
    """Starts and submits every subtest in order (except `skip`); returns the
    submit responses. Subtests in `wrong` get always-wrong answers."""
    bank = bank or v1_bank()
    answers = content_answers(bank, wrong=wrong)
    responses = []
    for subtest in sorted(bank.subtests, key=lambda s: s.number):
        if subtest.key in skip:
            continue
        if subtest.key == "lability":
            payload = quick_payload(bank)
        else:
            await client.post(
                f"/api/v1/assessment/{assessment_id}/astur/subtest/{subtest.number}/start", headers=headers
            )
            payload = {"answers": answers[subtest.key]}
        resp = await submit(client, assessment_id, subtest.number, payload, headers)
        assert resp.status_code == 201, resp.text
        responses.append(resp)
    return responses
