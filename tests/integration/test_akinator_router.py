import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.main import app
from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services.auth_service import create_jwt_token
from scripts.seed_akinator_content import seed_professions, seed_questions, seed_sections


async def _ensure_seeded(db: AsyncSession) -> None:
    section_ids, *_ = await seed_sections(db)
    await seed_professions(db, section_ids)
    await seed_questions(db)
    await db.flush()


async def _make_user_and_assessment(db: AsyncSession) -> tuple[User, Assessment]:
    user = User(email=f"{uuid.uuid4()}@test.local", hashed_password="x")
    db.add(user)
    await db.flush()

    profile = Profile(
        user_id=user.id, name="Test Student", age=16, grade=10,
        city="Test City", country="Test Country", language="ru",
        age_group=AgeGroup.senior,
    )
    db.add(profile)
    await db.flush()

    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()
    return user, assessment


def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_jwt_token(user_id)}"}


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def test_start_returns_a_direct_shallow_question(client: AsyncClient, db_session: AsyncSession):
    """AC1: POST .../start hands back a depth 0-1, direct question."""
    await _ensure_seeded(db_session)
    user, assessment = await _make_user_and_assessment(db_session)

    response = await client.post(
        f"/api/v1/assessment/{assessment.id}/akinator/start", headers=_auth_headers(user.id)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "next_question"
    assert uuid.UUID(body["question_id"])
    assert len(body["options"]) >= 2
    assert all({"index", "text"} <= set(opt) for opt in body["options"])
    assert "axis_weights" not in body["options"][0]  # scoring internals never leak to the client


async def test_sequential_answers_reach_a_valid_reveal(client: AsyncClient, db_session: AsyncSession):
    """AC2: repeated answer submissions eventually reach a valid reveal."""
    await _ensure_seeded(db_session)
    user, assessment = await _make_user_and_assessment(db_session)
    headers = _auth_headers(user.id)

    response = await client.post(f"/api/v1/assessment/{assessment.id}/akinator/start", headers=headers)
    body = response.json()

    turns = 0
    max_turns = settings.AKINATOR_CEILING_SENIOR + 1
    while body["type"] == "next_question":
        payload = {
            "question_id": body["question_id"],
            "selected_option_index": body["options"][0]["index"],
        }
        response = await client.post(
            f"/api/v1/assessment/{assessment.id}/akinator/answer", headers=headers, json=payload
        )
        assert response.status_code == 200
        body = response.json()
        turns += 1
        assert turns <= max_turns, "never reached a reveal within the age ceiling"

    assert body["type"] == "reveal"
    assert body["status"] in ("single", "cluster")
    assert len(body["leaves"]) >= 1
    assert all({"slug", "name"} <= set(leaf) for leaf in body["leaves"])


async def test_dont_know_answer_is_accepted(client: AsyncClient, db_session: AsyncSession):
    """selected_option_index=null ("не знаю") is a valid, accepted answer."""
    await _ensure_seeded(db_session)
    user, assessment = await _make_user_and_assessment(db_session)
    headers = _auth_headers(user.id)

    response = await client.post(f"/api/v1/assessment/{assessment.id}/akinator/start", headers=headers)
    body = response.json()

    response = await client.post(
        f"/api/v1/assessment/{assessment.id}/akinator/answer",
        headers=headers,
        json={"question_id": body["question_id"], "selected_option_index": None},
    )

    assert response.status_code == 200
    assert response.json()["type"] in ("next_question", "reveal")


async def test_accessing_someone_elses_assessment_is_forbidden(
    client: AsyncClient, db_session: AsyncSession
):
    """AC3: another user's assessment_id -> 403, not silently allowed."""
    await _ensure_seeded(db_session)
    _owner, assessment = await _make_user_and_assessment(db_session)
    intruder, _ = await _make_user_and_assessment(db_session)

    response = await client.post(
        f"/api/v1/assessment/{assessment.id}/akinator/start", headers=_auth_headers(intruder.id)
    )

    assert response.status_code == 403


async def test_unknown_assessment_is_not_found(client: AsyncClient, db_session: AsyncSession):
    await _ensure_seeded(db_session)
    user, _assessment = await _make_user_and_assessment(db_session)

    response = await client.post(
        f"/api/v1/assessment/{uuid.uuid4()}/akinator/start", headers=_auth_headers(user.id)
    )

    assert response.status_code == 404
