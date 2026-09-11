"""МАК v1 demo (PRO-314/315/318): session get-or-create, blind draw + no
repeat within a session, blank-followup rejection, and the `/result` `mac`
feed (populated for a psychologist viewer, null for the student — same role
gate as validity/psychoemotional, PRO-321)."""
import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.mac import MacExercise, MacSession
from app.models.profile import AgeGroup, Profile
from app.models.user import User, UserRole
from app.services import auth_service, mac_service, report_service


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


async def _e1(db: AsyncSession) -> MacExercise:
    row = (
        await db.execute(select(MacExercise).where(MacExercise.code == "E1"))
    ).scalar_one_or_none()
    assert row is not None, "seed_mac_exercises.py must have run against this DB"
    return row


async def test_create_session_is_idempotent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)

    first = await client.post(
        "/api/v1/mac/session", json={"assessment_id": str(assessment.id)}, headers=headers
    )
    assert first.status_code == 201
    body = first.json()
    assert body["completed"] is False
    codes = [e["code"] for e in body["exercises"]]
    assert "E1" in codes  # только активное упражнение отдаётся

    second = await client.post(
        "/api/v1/mac/session", json={"assessment_id": str(assessment.id)}, headers=headers
    )
    assert second.status_code == 201
    assert second.json()["session_id"] == body["session_id"]


async def test_draw_rejects_blank_followup_and_completes_session(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    session_id = (
        await client.post(
            "/api/v1/mac/session", json={"assessment_id": str(assessment.id)}, headers=headers
        )
    ).json()["session_id"]
    e1 = await _e1(db_session)

    drawn = await client.post(
        f"/api/v1/mac/session/{session_id}/draw",
        json={"exercise_id": str(e1.id)},
        headers=headers,
    )
    assert drawn.status_code == 200
    card = drawn.json()
    assert card["image_url"].endswith(".webp")
    assert card["image_url"].startswith("http")  # absolute — STORAGE_PUBLIC_BASE_URL + key

    blank = await client.post(
        "/api/v1/mac/response",
        json={
            "session_id": session_id,
            "exercise_id": str(e1.id),
            "card_ids": [card["id"]],
            "followup_answers": ["", "не пусто"],
        },
        headers=headers,
    )
    assert blank.status_code == 422

    real = await client.post(
        "/api/v1/mac/response",
        json={
            "session_id": session_id,
            "exercise_id": str(e1.id),
            "card_ids": [card["id"]],
            "followup_answers": ["Вижу лестницу.", "Похоже на мою цель."],
            "time_spent_ms": 15000,
            "revision_count": 2,
        },
        headers=headers,
    )
    assert real.status_code == 201
    assert real.json()["session_completed"] is True  # E1 — единственное активное


async def test_session_assessment_id_is_unique_at_the_db_level(
    db_session: AsyncSession,
) -> None:
    """Regression: a race between two `get_or_create_session` calls (React
    StrictMode's double-mount, or any client retry) used to slip past the old
    SELECT-then-INSERT and create two `mac_sessions` rows for one assessment
    — `_build_mac_section` then raised `MultipleResultsFound`, silently
    swallowed by the psych-block isolation try/except, so the psychologist
    just saw `mac: null` with no error anywhere. Fixed at the DB level
    (migration b7e3a5f9c1d4, `UNIQUE(assessment_id)`): repeated calls to
    `get_or_create_session` — the only way the app ever creates a row — must
    always resolve to the same one, never a second."""
    user, assessment, _ = await _auth(db_session)

    first = await mac_service.get_or_create_session(
        db_session, assessment_id=assessment.id, user_id=user.id
    )
    for _ in range(4):
        again = await mac_service.get_or_create_session(
            db_session, assessment_id=assessment.id, user_id=user.id
        )
        assert again.id == first.id

    rows = (
        await db_session.execute(
            select(MacSession).where(MacSession.assessment_id == assessment.id)
        )
    ).scalars().all()
    assert len(rows) == 1


async def test_blind_draw_never_repeats_within_a_session(db_session: AsyncSession) -> None:
    user, assessment, _ = await _auth(db_session)
    session = await mac_service.get_or_create_session(
        db_session, assessment_id=assessment.id, user_id=user.id
    )
    e1 = await _e1(db_session)

    first_card = await mac_service.draw_blind_card(
        db_session, session_id=session.id, exercise_id=e1.id, user_id=user.id
    )
    from app.schemas.mac import SubmitMacResponseRequest
    await mac_service.submit_response(
        db_session,
        SubmitMacResponseRequest(
            session_id=session.id, exercise_id=e1.id, card_ids=[first_card.id],
            followup_answers=["a", "b"],
        ),
        user_id=user.id,
    )

    # Тот же вызов должен исключить уже выпавшую карту — прогоняем много раз,
    # чтобы не полагаться на удачу random.choice.
    for _ in range(30):
        again = await mac_service.draw_blind_card(
            db_session, session_id=session.id, exercise_id=e1.id, user_id=user.id
        )
        assert again.id != first_card.id


async def test_mac_section_populated_for_psychologist_null_for_student(
    db_session: AsyncSession,
) -> None:
    user, assessment, _ = await _auth(db_session)

    before = await report_service._build_mac_section(assessment.id, db_session, consent_ok=False)
    assert before is None

    session = await mac_service.get_or_create_session(
        db_session, assessment_id=assessment.id, user_id=user.id
    )
    e1 = await _e1(db_session)
    card = await mac_service.draw_blind_card(
        db_session, session_id=session.id, exercise_id=e1.id, user_id=user.id
    )
    from app.schemas.mac import SubmitMacResponseRequest
    await mac_service.submit_response(
        db_session,
        SubmitMacResponseRequest(
            session_id=session.id, exercise_id=e1.id, card_ids=[card.id],
            followup_answers=["Вижу лестницу.", "Похоже на мою цель."],
        ),
        user_id=user.id,
    )

    after = await report_service._build_mac_section(assessment.id, db_session, consent_ok=False)
    assert after is not None
    assert after.completed is True
    assert len(after.feed) == 1
    item = after.feed[0]
    assert item.exercise_code == "E1"
    from app.integrations.storage.urls import build_public_url
    assert item.card_image_urls == [build_public_url(card.image_path)]
    assert item.followup_answers == ["Вижу лестницу.", "Похоже на мою цель."]

    # Гейт секции (PRO-321) — тот же переключатель, что у validity/psychoemotional.
    assert report_service.psych_sections_for(UserRole.psychologist, assessment_id=assessment.id)
    assert not report_service.psych_sections_for(UserRole.student, assessment_id=assessment.id)
