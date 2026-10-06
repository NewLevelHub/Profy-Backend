"""PROFY-005: duplicate identifiers are rejected before bulk upserts."""

from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.motivation import MotivationResponse, MotivationStatement
from app.models.question import Question, QuestionInstrument
from app.models.question_pair import QuestionPair
from app.models.user_response import UserResponse
from tests.integration.astur_helpers import make_student


def _assert_duplicate_error(response: Response, error_code: str) -> None:
    assert response.status_code == 422, response.text
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", "answers"]
    assert error["type"] == error_code


async def test_duplicate_question_id_rejects_the_whole_batch(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _user, assessment, headers = await make_student(db_session)
    question_ids = list(
        (
            await db_session.execute(
                select(Question.id)
                .where(Question.instrument == QuestionInstrument.riasec)
                .order_by(Question.order)
                .limit(2)
            )
        ).scalars()
    )
    assert len(question_ids) == 2

    response = await client.post(
        f"/api/v1/assessment/{assessment.id}/answers",
        json={
            "answers": [
                {"question_id": str(question_ids[0]), "value": 4},
                {"question_id": str(question_ids[1]), "value": 2},
                {"question_id": str(question_ids[1]), "value": 5},
            ]
        },
        headers=headers,
    )

    _assert_duplicate_error(response, "duplicate_question_ids")
    stored = (
        await db_session.execute(
            select(UserResponse).where(
                UserResponse.assessment_id == assessment.id
            )
        )
    ).scalars().all()
    assert stored == []


async def test_duplicate_pair_index_rejects_the_whole_batch(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _user, assessment, headers = await make_student(db_session)
    pair = (
        await db_session.execute(
            select(QuestionPair)
            .where(QuestionPair.instrument != QuestionInstrument.big_five)
            .order_by(QuestionPair.pair_index)
            .limit(1)
        )
    ).scalar_one()

    response = await client.post(
        f"/api/v1/assessment/{assessment.id}/pair-answers",
        json={
            "answers": [
                {
                    "pair_index": pair.pair_index,
                    "picked_question_id": str(pair.question_a_id),
                },
                {
                    "pair_index": pair.pair_index,
                    "picked_question_id": str(pair.question_b_id),
                },
            ]
        },
        headers=headers,
    )

    _assert_duplicate_error(response, "duplicate_pair_indexes")
    stored = (
        await db_session.execute(
            select(UserResponse).where(
                UserResponse.assessment_id == assessment.id
            )
        )
    ).scalars().all()
    assert stored == []


async def test_duplicate_triplet_index_rejects_the_whole_batch(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _user, assessment, headers = await make_student(db_session)
    statements = (
        await db_session.execute(
            select(MotivationStatement).order_by(
                MotivationStatement.triplet_index, MotivationStatement.order
            )
        )
    ).scalars().all()
    assert statements
    triplet_index = statements[0].triplet_index
    triplet = [
        statement
        for statement in statements
        if statement.triplet_index == triplet_index
    ]
    assert len(triplet) == 3

    response = await client.post(
        f"/api/v1/assessment/{assessment.id}/motivation-answers",
        json={
            "answers": [
                {
                    "triplet_index": triplet_index,
                    "most_statement_id": str(triplet[0].id),
                    "least_statement_id": str(triplet[1].id),
                },
                {
                    "triplet_index": triplet_index,
                    "most_statement_id": str(triplet[1].id),
                    "least_statement_id": str(triplet[2].id),
                },
            ]
        },
        headers=headers,
    )

    _assert_duplicate_error(response, "duplicate_triplet_indexes")
    stored = (
        await db_session.execute(
            select(MotivationResponse).where(
                MotivationResponse.assessment_id == assessment.id
            )
        )
    ).scalars().all()
    assert stored == []
