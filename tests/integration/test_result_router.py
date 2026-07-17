import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.main import app
from app.models.assessment import Assessment, AssessmentGoal
from app.models.assessment_session import AssessmentSession
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services.auth_service import create_jwt_token
from scripts.seed_akinator_content import seed_professions, seed_questions, seed_sections
from scripts.seed_astana_universities import main as seed_astana_universities


async def _ensure_seeded(db: AsyncSession) -> None:
    section_ids, *_ = await seed_sections(db)
    await seed_professions(db, section_ids)
    await seed_questions(db)
    await db.flush()
    await seed_astana_universities()


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

    session = AssessmentSession(assessment_id=assessment.id)
    db.add(session)
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


async def _run_to_liked_result(
    client: AsyncClient, assessment_id: uuid.UUID, headers: dict[str, str]
) -> str:
    """Drive a session to reveal (always picking option 0), like it, and
    return the winning slug."""
    response = await client.post(f"/api/v1/assessment/{assessment_id}/akinator/start", headers=headers)
    body = response.json()

    max_turns = settings.AKINATOR_CEILING_SENIOR + 1
    turns = 0
    while body["type"] == "next_question":
        payload = {
            "question_id": body["question_id"],
            "selected_option_index": body["options"][0]["index"],
        }
        response = await client.post(
            f"/api/v1/assessment/{assessment_id}/akinator/answer", headers=headers, json=payload
        )
        body = response.json()
        turns += 1
        assert turns <= max_turns, "never reached a reveal within the age ceiling"

    assert body["type"] == "reveal"
    winner_slug = body["leaves"][0]["slug"]

    feedback = await client.post(
        f"/api/v1/assessment/{assessment_id}/akinator/feedback",
        headers=headers,
        json={"liked": True, "note": None},
    )
    assert feedback.status_code == 200
    return winner_slug


async def test_result_is_404_before_the_test_is_completed(client: AsyncClient, db_session: AsyncSession):
    """AC2: no reveal/feedback yet -> 404, not 500 and not an empty 200."""
    await _ensure_seeded(db_session)
    user, assessment = await _make_user_and_assessment(db_session)

    response = await client.get(f"/api/v1/result/{assessment.id}", headers=_auth_headers(user.id))

    assert response.status_code == 404


async def test_result_is_available_after_a_liked_reveal(client: AsyncClient, db_session: AsyncSession):
    """AC1: 200 with the confirmed direction, matched axes, and university suggestions."""
    await _ensure_seeded(db_session)
    user, assessment = await _make_user_and_assessment(db_session)
    headers = _auth_headers(user.id)

    winner_slug = await _run_to_liked_result(client, assessment.id, headers)

    response = await client.get(f"/api/v1/result/{assessment.id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["assessment_id"] == str(assessment.id)
    assert body["direction_slug"] == winner_slug
    assert body["direction_name"]
    assert body["message"]
    assert isinstance(body["matched_axes"], list)
    assert len(body["matched_axes"]) >= 1
    assert isinstance(body["recommended_programs"], list)
    assert len(body["recommended_programs"]) >= 1
    for axis in body["matched_axes"]:
        assert {"code", "label_ru", "direction_value"} <= set(axis)
        assert -2 <= axis["direction_value"] <= 2
        assert axis["direction_value"] != 0
    for program in body["recommended_programs"]:
        assert {"id", "name", "language", "direction_slug", "university"} <= set(program)
        assert {"name", "country", "city"} <= set(program["university"])
        assert program["university"]["city"] == "Астана"

    # AC5: the child's own strengths/growth areas, from real answers given
    # during the run (always option 0 — see _run_to_liked_result), not from
    # the profession's own axis profile.
    assert isinstance(body["strengths"], list)
    assert isinstance(body["growth_areas"], list)
    assert len(body["strengths"]) + len(body["growth_areas"]) >= 1
    for signal in [*body["strengths"], *body["growth_areas"]]:
        assert {"code", "label_ru", "score"} <= set(signal)
    for signal in body["strengths"]:
        assert signal["score"] > 0
    for signal in body["growth_areas"]:
        assert signal["score"] < 0


async def test_result_of_another_users_assessment_is_forbidden(
    client: AsyncClient, db_session: AsyncSession
):
    """AC4-adjacent access check, same pattern as roadmap/akinator routers."""
    await _ensure_seeded(db_session)
    _owner, assessment = await _make_user_and_assessment(db_session)
    intruder, _ = await _make_user_and_assessment(db_session)

    response = await client.get(
        f"/api/v1/result/{assessment.id}", headers=_auth_headers(intruder.id)
    )

    assert response.status_code == 403


async def test_result_of_unknown_assessment_is_not_found(client: AsyncClient, db_session: AsyncSession):
    await _ensure_seeded(db_session)
    user, _assessment = await _make_user_and_assessment(db_session)

    response = await client.get(
        f"/api/v1/result/{uuid.uuid4()}", headers=_auth_headers(user.id)
    )

    assert response.status_code == 404
