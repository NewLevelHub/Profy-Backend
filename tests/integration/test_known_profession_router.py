import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.main import app
from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.assessment_session import AssessmentSession
from app.models.direction import Direction
from app.models.known_profession_quiz import KnownProfessionQuiz
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import roadmap_builder
from app.services.auth_service import create_jwt_token
from scripts.seed_akinator_content import seed_questions, seed_sections, seed_specialties

SLUG = "software-engineer"

QUESTIONS = [
    {
        "id": "q1",
        "kind": "situational",
        "text": "Несколько часов подряд собираешь что-то из логики и правил.",
        "options": [
            {"text": "Обожаю такое состояние потока", "fit_score": 2},
            {"text": "Нормально, если задача интересная", "fit_score": 1},
            {"text": "Быстро надоедает", "fit_score": 0},
        ],
    },
    {
        "id": "q2",
        "kind": "commitment",
        "text": "Учиться придётся постоянно, всю карьеру.",
        "options": [
            {"text": "Готов(а)", "fit_score": 2},
            {"text": "Норм в разумных пределах", "fit_score": 1},
            {"text": "Хочу выучиться один раз и всё", "fit_score": 0},
        ],
    },
]


async def _ensure_seeded(db: AsyncSession) -> None:
    section_ids, *_ = await seed_sections(db)
    await seed_specialties(db, section_ids)
    await seed_questions(db)

    # Upsert, not insert: the real seed script (scripts/seed_known_profession_quizzes.py)
    # may already have a row for SLUG in this DB (tests run against the same
    # database, isolated only by a per-test rollback — see conftest.db_session),
    # so a blind insert would collide with already-committed real content.
    existing = (
        await db.execute(select(KnownProfessionQuiz).where(KnownProfessionQuiz.leaf_slug == SLUG))
    ).scalar_one_or_none()
    if existing is None:
        db.add(KnownProfessionQuiz(leaf_slug=SLUG, questions=QUESTIONS))
    else:
        existing.questions = QUESTIONS
    await db.flush()


NO_QUIZ_SLUG = "test-leaf-no-quiz"


async def _make_leaf_direction_without_quiz(db: AsyncSession) -> None:
    """A real leaf Direction with no KnownProfessionQuiz row — distinct from
    an unknown slug, and safe against seed_known_profession_quizzes.py having
    already seeded quizzes for all 57 real catalog specialties in this DB
    (tests run against that same database — see conftest.db_session)."""
    existing = (
        await db.execute(select(Direction).where(Direction.slug == NO_QUIZ_SLUG))
    ).scalar_one_or_none()
    if existing is None:
        db.add(Direction(name="Test Leaf", slug=NO_QUIZ_SLUG, description="Test fixture leaf."))
        await db.flush()


async def _make_user(db: AsyncSession, age_group: AgeGroup = AgeGroup.senior) -> tuple[User, Profile]:
    user = User(email=f"{uuid.uuid4()}@test.local", hashed_password="x")
    db.add(user)
    await db.flush()

    profile = Profile(
        user_id=user.id, name="Test Student", age=16, grade=10,
        city="Астана", country="Казахстан", language="ru",
        age_group=age_group,
    )
    db.add(profile)
    await db.flush()
    return user, profile


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


async def test_get_quiz_returns_seeded_questions(client: AsyncClient, db_session: AsyncSession):
    await _ensure_seeded(db_session)

    response = await client.get(f"/api/v1/directions/{SLUG}/known-profession-quiz")

    assert response.status_code == 200
    body = response.json()
    assert body["leaf_slug"] == SLUG
    assert len(body["questions"]) == 2


async def test_get_quiz_is_not_found_for_unseeded_direction(client: AsyncClient, db_session: AsyncSession):
    await _ensure_seeded(db_session)
    await _make_leaf_direction_without_quiz(db_session)

    response = await client.get(f"/api/v1/directions/{NO_QUIZ_SLUG}/known-profession-quiz")

    assert response.status_code == 404


async def test_finalize_creates_sessionless_completed_assessment(
    client: AsyncClient, db_session: AsyncSession
):
    await _ensure_seeded(db_session)
    user, _profile = await _make_user(db_session)
    await db_session.commit()

    response = await client.post(
        "/api/v1/assessment/known-profession/finalize",
        headers=_auth_headers(user.id),
        json={"direction_slug": SLUG, "answers": {"q1": 0, "q2": 0}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["percent"] == 100
    assert body["verdict"] == "strong"

    assessment = await db_session.get(Assessment, uuid.UUID(body["assessment_id"]))
    assert assessment is not None
    assert assessment.status == AssessmentStatus.completed
    assert assessment.selected_direction_slug == SLUG
    assert assessment.goal == AssessmentGoal.known

    session_result = await db_session.execute(
        select(AssessmentSession).where(AssessmentSession.assessment_id == assessment.id)
    )
    assert session_result.scalar_one_or_none() is None


async def test_finalize_without_quiz_is_not_found(client: AsyncClient, db_session: AsyncSession):
    await _ensure_seeded(db_session)
    await _make_leaf_direction_without_quiz(db_session)
    user, _profile = await _make_user(db_session)
    await db_session.commit()

    response = await client.post(
        "/api/v1/assessment/known-profession/finalize",
        headers=_auth_headers(user.id),
        json={"direction_slug": NO_QUIZ_SLUG, "answers": {}},
    )

    assert response.status_code == 404


async def test_finalize_abandons_prior_in_progress_assessment(
    client: AsyncClient, db_session: AsyncSession
):
    await _ensure_seeded(db_session)
    user, profile = await _make_user(db_session)
    stale = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db_session.add(stale)
    await db_session.commit()

    response = await client.post(
        "/api/v1/assessment/known-profession/finalize",
        headers=_auth_headers(user.id),
        json={"direction_slug": SLUG, "answers": {"q1": 0, "q2": 0}},
    )

    assert response.status_code == 200
    await db_session.refresh(stale)
    assert stale.status == AssessmentStatus.abandoned


async def test_result_is_available_after_finalize_without_a_session(
    client: AsyncClient, db_session: AsyncSession
):
    """The known-profession flow never runs the belief-walk engine, so
    /result must degrade gracefully (empty axis comparison/backups) instead
    of the 404 it used to raise when no AssessmentSession existed."""
    await _ensure_seeded(db_session)
    user, _profile = await _make_user(db_session)
    await db_session.commit()
    headers = _auth_headers(user.id)

    finalize_response = await client.post(
        "/api/v1/assessment/known-profession/finalize",
        headers=headers,
        json={"direction_slug": SLUG, "answers": {"q1": 1, "q2": 1}},
    )
    assessment_id = finalize_response.json()["assessment_id"]

    response = await client.get(f"/api/v1/result/{assessment_id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["direction_slug"] == SLUG
    assert body["direction_name"]
    assert body["message"]
    assert body["matches"] == []
    assert body["growth_areas"] == []
    assert body["is_direction_specific"] is False
    assert body["backups"] == []
    assert isinstance(body["recommended_programs"], list)


async def test_roadmap_access_allowed_after_known_profession_finalize(
    client: AsyncClient, db_session: AsyncSession
):
    """Confirms the sessionless Assessment this flow creates plugs straight
    into the existing roadmap pipeline — no roadmap_builder changes needed."""
    await _ensure_seeded(db_session)
    user, _profile = await _make_user(db_session)
    await db_session.commit()
    headers = _auth_headers(user.id)

    finalize_response = await client.post(
        "/api/v1/assessment/known-profession/finalize",
        headers=headers,
        json={"direction_slug": SLUG, "answers": {"q1": 0, "q2": 0}},
    )
    assessment_id = uuid.UUID(finalize_response.json()["assessment_id"])

    result_assessment, direction = await roadmap_builder._require_direction_roadmap_access(
        assessment_id, SLUG, db_session
    )

    assert result_assessment.id == assessment_id
    assert direction.slug == SLUG
