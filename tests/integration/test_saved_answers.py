"""GET /assessment/{id}/saved-answers — reads back what the main battery and
motivation already stored, so the client can show earlier answers on
"Назад" even when it lost its own copy (new tab, another device). Without
it the frontend showed answered pages blank, and motivation re-sent the
default card order over the student's real ranking."""
import uuid

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.motivation import MotivationCategory, MotivationStatement
from app.models.profile import AgeGroup, Profile
from app.models.question import Question, QuestionInstrument
from app.models.question_pair import QuestionPair
from app.models.user import User
from app.schemas.motivation import MotivationAnswerItem
from app.schemas.question_pair import PairAnswerItem
from app.schemas.response import AnswerItem
from app.services import assessment_service, auth_service, motivation_service, question_pair_service

# Far outside the seeded banks' ranges, so the test's own rows never collide
# with the content already in the database.
PAIR_INDEX = 9001
TRIPLET_INDEX = 9001


async def _make_assessment(db: AsyncSession) -> Assessment:
    assessment, _ = await _make_assessment_with_user(db)
    return assessment


async def _make_assessment_with_user(db: AsyncSession) -> tuple[Assessment, User]:
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x", is_active=True, is_verified=True)
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
    return assessment, user


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {auth_service.create_jwt_token(user.id)}"}


async def _seed(db: AsyncSession) -> dict:
    def question(order: int) -> Question:
        return Question(instrument=QuestionInstrument.riasec, text={"ru": f"q{order}", "kk": f"q{order}"}, order=90_000 + order)

    likert, option_a, option_b = question(1), question(2), question(3)
    db.add_all([likert, option_a, option_b])
    await db.flush()
    db.add(QuestionPair(
        instrument=QuestionInstrument.professional_types, pair_index=PAIR_INDEX,
        question_a_id=option_a.id, question_b_id=option_b.id,
    ))
    statements = [
        MotivationStatement(triplet_index=TRIPLET_INDEX, order=i, category=category, text={"ru": f"s{i}", "kk": f"s{i}"})
        for i, category in enumerate(list(MotivationCategory)[:3])
    ]
    db.add_all(statements)
    await db.flush()
    return {"likert": likert, "a": option_a, "b": option_b, "statements": statements}


async def test_saved_answers_echo_scale_pair_and_motivation(db_session: AsyncSession) -> None:
    seeded = await _seed(db_session)
    assessment = await _make_assessment(db_session)
    profile_id = assessment.profile_id
    most, _, least = seeded["statements"]

    await assessment_service.submit_answers(
        assessment.id, [AnswerItem(question_id=seeded["likert"].id, value=4)], profile_id, db_session,
    )
    await question_pair_service.submit_pair_answers(
        assessment.id, [PairAnswerItem(pair_index=PAIR_INDEX, picked_question_id=seeded["b"].id)], profile_id, db_session,
    )
    await motivation_service.submit_motivation_answers(
        assessment.id,
        [MotivationAnswerItem(triplet_index=TRIPLET_INDEX, most_statement_id=most.id, least_statement_id=least.id)],
        profile_id,
        db_session,
    )

    saved = await assessment_service.get_saved_answers(assessment.id, profile_id, db_session)

    assert saved.question_values[seeded["likert"].id] == 4
    assert saved.pair_picks == {PAIR_INDEX: seeded["b"].id}
    # The pair's synthetic 5/1 rows aren't scale answers — never echoed as such.
    assert seeded["a"].id not in saved.question_values
    assert seeded["b"].id not in saved.question_values
    assert saved.motivation[TRIPLET_INDEX].most_statement_id == most.id
    assert saved.motivation[TRIPLET_INDEX].least_statement_id == least.id


async def test_a_changed_pick_reads_back_as_the_new_one(db_session: AsyncSession) -> None:
    seeded = await _seed(db_session)
    assessment = await _make_assessment(db_session)
    for picked in (seeded["a"], seeded["b"]):
        await question_pair_service.submit_pair_answers(
            assessment.id, [PairAnswerItem(pair_index=PAIR_INDEX, picked_question_id=picked.id)],
            assessment.profile_id, db_session,
        )

    saved = await assessment_service.get_saved_answers(assessment.id, assessment.profile_id, db_session)

    assert saved.pair_picks == {PAIR_INDEX: seeded["b"].id}


async def test_fresh_assessment_has_nothing_saved(db_session: AsyncSession) -> None:
    assessment = await _make_assessment(db_session)

    saved = await assessment_service.get_saved_answers(assessment.id, assessment.profile_id, db_session)

    assert saved.question_values == {}
    assert saved.pair_picks == {}
    assert saved.motivation == {}


async def test_someone_elses_assessment_is_forbidden(db_session: AsyncSession) -> None:
    assessment = await _make_assessment(db_session)
    stranger = await _make_assessment(db_session)

    with pytest.raises(HTTPException) as exc:
        await assessment_service.get_saved_answers(assessment.id, stranger.profile_id, db_session)

    assert exc.value.status_code == 403


async def test_endpoint_returns_the_saved_answers_over_http(client: AsyncClient, db_session: AsyncSession) -> None:
    """The route, its auth dependency and the response_model serialization —
    JSON object keys come out as strings for both uuid and int keys."""
    seeded = await _seed(db_session)
    assessment, user = await _make_assessment_with_user(db_session)
    most, _, least = seeded["statements"]
    await question_pair_service.submit_pair_answers(
        assessment.id, [PairAnswerItem(pair_index=PAIR_INDEX, picked_question_id=seeded["a"].id)],
        assessment.profile_id, db_session,
    )
    await motivation_service.submit_motivation_answers(
        assessment.id,
        [MotivationAnswerItem(triplet_index=TRIPLET_INDEX, most_statement_id=most.id, least_statement_id=least.id)],
        assessment.profile_id,
        db_session,
    )

    resp = await client.get(f"/api/v1/assessment/{assessment.id}/saved-answers", headers=_auth(user))

    assert resp.status_code == 200
    body = resp.json()
    assert body["pair_picks"] == {str(PAIR_INDEX): str(seeded["a"].id)}
    assert body["motivation"] == {
        str(TRIPLET_INDEX): {"most_statement_id": str(most.id), "least_statement_id": str(least.id)},
    }
    assert str(seeded["a"].id) not in body["question_values"]


async def test_endpoint_refuses_strangers_and_anonymous(client: AsyncClient, db_session: AsyncSession) -> None:
    assessment, _ = await _make_assessment_with_user(db_session)
    _, stranger = await _make_assessment_with_user(db_session)
    url = f"/api/v1/assessment/{assessment.id}/saved-answers"

    assert (await client.get(url, headers=_auth(stranger))).status_code == 403
    assert (await client.get(url)).status_code == 401
