import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.main import app
from app.models.akinator_question import AkinatorQuestion
from app.models.assessment import Assessment, AssessmentGoal
from app.models.assessment_session import AssessmentSession, SessionStatus
from app.models.direction import Direction
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services.auth_service import create_jwt_token
from scripts.seed_akinator_content import seed_questions, seed_sections, seed_specialties


async def _ensure_seeded(db: AsyncSession) -> None:
    section_ids, *_ = await seed_sections(db)
    await seed_specialties(db, section_ids)
    await seed_questions(db)
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


async def test_resolve_cluster_flow_psychologist_vs_speech_therapist(
    client: AsyncClient, db_session: AsyncSession
):
    """AC2: Manual verification on psychologist vs speech-therapist pair (q20, order 19)."""
    await _ensure_seeded(db_session)
    user, assessment = await _make_user_and_assessment(db_session)
    headers = _auth_headers(user.id)

    # 1. Start akinator session
    start_resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/akinator/start", headers=headers
    )
    assert start_resp.status_code == 200

    # 2. Artificially change status to converged_cluster and set flat belief
    # with psychologist and speech-therapist as leaders
    sess = (
        await db_session.execute(
            select(AssessmentSession).where(
                AssessmentSession.assessment_id == assessment.id
            )
        )
    ).scalar_one()

    leaves = (
        await db_session.execute(select(Direction.slug).where(Direction.is_leaf.is_(True)))
    ).scalars().all()

    belief = {
        "psychologist": 0.40,
        "speech-therapist": 0.40,
    }
    other_leaves = [l for l in leaves if l not in {"psychologist", "speech-therapist"}]
    tiny_p = 0.20 / len(other_leaves)
    for l in other_leaves:
        belief[l] = tiny_p

    # normalize belief
    total = sum(belief.values())
    belief = {k: v / total for k, v in belief.items()}

    sess.belief = belief
    sess.status = SessionStatus.converged_cluster
    db_session.add(sess)
    await db_session.commit()

    # 3. Call POST /resolve without parameters to get the next resolver question
    resolve_resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/akinator/resolve",
        headers=headers,
        json={},
    )
    assert resolve_resp.status_code == 200
    body = resolve_resp.json()
    assert body["type"] == "next_question"
    
    # Check that this is the psychologist vs speech-therapist question (order 19, text containing q20 help)
    q_id = body["question_id"]
    q = await db_session.get(AkinatorQuestion, uuid.UUID(q_id))
    assert q is not None
    assert q.order == 19
    assert set(q.resolves_pair) == {"psychologist", "speech-therapist"}

    # 4. Submit answer to option 0 (picks psychologist helper axis)
    answer_resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/akinator/resolve",
        headers=headers,
        json={
            "question_id": q_id,
            "selected_option_index": 0,
        },
    )
    assert answer_resp.status_code == 200
    body = answer_resp.json()
    
    # Reload session and assert resolve_step = 1 and belief is updated in database
    await db_session.refresh(sess)
    assert sess.resolve_step == 1
    assert sess.belief["psychologist"] > sess.belief["speech-therapist"]
