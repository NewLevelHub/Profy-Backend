import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.main import app
from app.models.assessment import Assessment, AssessmentGoal
from app.models.assessment_session import AssessmentSession
from app.models.direction import Direction
from app.models.profile import AgeGroup, Profile
from app.models.profession_simulation import ProfessionSimulation
from app.models.profession_simulation_log import ProfessionSimulationLog
from app.models.user import User
from app.services.auth_service import create_jwt_token
from scripts.seed_akinator_content import seed_professions, seed_questions, seed_sections
from scripts.seed_simulations import seed_simulations


async def _ensure_seeded(db: AsyncSession) -> None:
    section_ids, *_ = await seed_sections(db)
    await seed_professions(db, section_ids)
    await seed_questions(db)
    await seed_simulations()
    await db.flush()


async def _make_user_and_assessment(db: AsyncSession) -> tuple[User, Assessment]:
    user = User(email=f"{uuid.uuid4()}@test.local", hashed_password="x")
    db.add(user)
    await db.flush()

    profile = Profile(
        user_id=user.id,
        name="Test Student",
        age=16,
        grade=10,
        city="Test City",
        country="Test Country",
        language="ru",
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


async def _run_to_reveal(
    client: AsyncClient, assessment_id: uuid.UUID, headers: dict[str, str]
) -> dict:
    response = await client.post(
        f"/api/v1/assessment/{assessment_id}/akinator/start", headers=headers
    )
    body = response.json()

    while body["type"] == "next_question":
        payload = {
            "question_id": body["question_id"],
            "selected_option_index": body["options"][0]["index"],
        }
        response = await client.post(
            f"/api/v1/assessment/{assessment_id}/akinator/answer",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 200
        body = response.json()

    return body


async def test_get_simulation_success_and_errors(client: AsyncClient, db_session: AsyncSession):
    await _ensure_seeded(db_session)
    user, assessment = await _make_user_and_assessment(db_session)
    headers = _auth_headers(user.id)

    # 1. Success case
    resp = await client.get(
        f"/api/v1/assessment/{assessment.id}/simulation/programmer",
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["leaf_slug"] == "programmer"
    assert len(body["steps"]) == 2
    assert body["steps"][0]["text"]

    # 2. 404 Case (simulation not found)
    resp = await client.get(
        f"/api/v1/assessment/{assessment.id}/simulation/non-existent-leaf",
        headers=headers,
    )
    assert resp.status_code == 404

    # 3. 403 Case (wrong user)
    other_user, _ = await _make_user_and_assessment(db_session)
    other_headers = _auth_headers(other_user.id)
    resp = await client.get(
        f"/api/v1/assessment/{assessment.id}/simulation/programmer",
        headers=other_headers,
    )
    assert resp.status_code == 403


async def test_submit_simulation_accepted_saves_log_keeps_belief(
    client: AsyncClient, db_session: AsyncSession
):
    await _ensure_seeded(db_session)
    user, assessment = await _make_user_and_assessment(db_session)
    headers = _auth_headers(user.id)

    # Start akinator session to initialize belief
    start_resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/akinator/start", headers=headers
    )
    assert start_resp.status_code == 200

    # Get belief before simulation
    sess = (
        await db_session.execute(
            select(AssessmentSession).where(
                AssessmentSession.assessment_id == assessment.id
            )
        )
    ).scalar_one()
    belief_before = dict(sess.belief)

    # Submit accepted=True
    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/simulation/programmer/submit",
        headers=headers,
        json={"accepted": True, "answers": [0, 1]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "recorded"
    assert body["akinator_turn"] is None

    # Check log is written in DB
    log = (
        await db_session.execute(
            select(ProfessionSimulationLog).where(
                ProfessionSimulationLog.assessment_id == assessment.id,
                ProfessionSimulationLog.leaf_slug == "programmer",
            )
        )
    ).scalar_one_or_none()
    assert log is not None
    assert log.accepted is True
    assert log.answers == [0, 1]

    # Verify belief is unchanged
    await db_session.refresh(sess)
    assert sess.belief == belief_before


async def test_submit_simulation_rejected_updates_belief_negatively(
    client: AsyncClient, db_session: AsyncSession
):
    await _ensure_seeded(db_session)
    user, assessment = await _make_user_and_assessment(db_session)
    headers = _auth_headers(user.id)

    # Start akinator session to initialize belief
    start_resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/akinator/start", headers=headers
    )
    assert start_resp.status_code == 200

    # Ensure programmer is in belief
    sess = (
        await db_session.execute(
            select(AssessmentSession).where(
                AssessmentSession.assessment_id == assessment.id
            )
        )
    ).scalar_one()
    assert "programmer" in sess.belief
    programmer_belief_before = sess.belief["programmer"]
    assert programmer_belief_before > 0.001

    # Submit accepted=False (rejection)
    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/simulation/programmer/submit",
        headers=headers,
        json={"accepted": False, "answers": [0, 1]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "recorded"
    assert body["akinator_turn"] is not None  # it recalculates akinator state and returns turn

    # Verify simulation log
    log = (
        await db_session.execute(
            select(ProfessionSimulationLog).where(
                ProfessionSimulationLog.assessment_id == assessment.id,
                ProfessionSimulationLog.leaf_slug == "programmer",
            )
        )
    ).scalar_one_or_none()
    assert log is not None
    assert log.accepted is False

    # Verify belief for programmer dropped to near zero
    await db_session.refresh(sess)
    assert sess.belief["programmer"] < 1e-10
