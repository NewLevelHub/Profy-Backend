"""PROFY-003: answer values are validated against their instrument scale."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question, QuestionInstrument
from app.models.user_response import UserResponse
from tests.integration.astur_helpers import make_student


async def _question(
    db: AsyncSession,
    instrument: QuestionInstrument,
    order: int,
) -> Question:
    question = Question(
        instrument=instrument,
        text={"ru": f"PROFY-003 {instrument.value} {order}"},
        order=order,
    )
    db.add(question)
    await db.flush()
    return question


async def _stored_answers(
    db: AsyncSession, assessment_id
) -> list[UserResponse]:
    return list(
        (
            await db.execute(
                select(UserResponse).where(
                    UserResponse.assessment_id == assessment_id
                )
            )
        ).scalars()
    )


@pytest.mark.parametrize(
    ("instrument", "invalid_value"),
    [
        (QuestionInstrument.riasec, 0),
        (QuestionInstrument.professional_types_abilities, 4),
        (QuestionInstrument.eysenck, 3),
        (QuestionInstrument.elers, 3),
        (QuestionInstrument.boyko_empathy, 3),
        (QuestionInstrument.kondash_anxiety, 5),
    ],
)
async def test_answers_endpoint_rejects_values_outside_the_instrument_scale(
    client: AsyncClient,
    db_session: AsyncSession,
    instrument: QuestionInstrument,
    invalid_value: int,
) -> None:
    _user, assessment, headers = await make_student(db_session)
    question = await _question(db_session, instrument, order=990_001)

    response = await client.post(
        f"/api/v1/assessment/{assessment.id}/answers",
        json={
            "answers": [
                {"question_id": str(question.id), "value": invalid_value}
            ]
        },
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "answer_value_invalid_for_instrument"
    assert await _stored_answers(db_session, assessment.id) == []


async def test_answers_endpoint_accepts_both_boundaries_of_every_active_scale(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _user, assessment, headers = await make_student(db_session)
    boundaries = {
        QuestionInstrument.riasec: (1, 5),
        QuestionInstrument.professional_types_abilities: (0, 3),
        QuestionInstrument.eysenck: (1, 2),
        QuestionInstrument.elers: (1, 2),
        QuestionInstrument.boyko_empathy: (1, 2),
        QuestionInstrument.kondash_anxiety: (0, 4),
    }
    payload: list[dict[str, str | int]] = []
    expected: dict = {}
    for instrument_index, (instrument, values) in enumerate(boundaries.items()):
        for value_index, value in enumerate(values):
            question = await _question(
                db_session,
                instrument,
                order=991_000 + instrument_index * 10 + value_index,
            )
            payload.append({"question_id": str(question.id), "value": value})
            expected[question.id] = value

    response = await client.post(
        f"/api/v1/assessment/{assessment.id}/answers",
        json={"answers": payload},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    stored = await _stored_answers(db_session, assessment.id)
    assert {item.question_id: item.answer_value for item in stored} == expected


async def test_invalid_value_rejects_the_whole_mixed_batch_atomically(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _user, assessment, headers = await make_student(db_session)
    valid_question = await _question(
        db_session, QuestionInstrument.riasec, order=992_001
    )
    invalid_question = await _question(
        db_session, QuestionInstrument.eysenck, order=992_002
    )

    response = await client.post(
        f"/api/v1/assessment/{assessment.id}/answers",
        json={
            "answers": [
                {"question_id": str(valid_question.id), "value": 5},
                {"question_id": str(invalid_question.id), "value": 5},
            ]
        },
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "answer_value_invalid_for_instrument"
    assert await _stored_answers(db_session, assessment.id) == []


async def test_pair_question_cannot_be_submitted_as_a_scalar_answer(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _user, assessment, headers = await make_student(db_session)
    question = await _question(
        db_session, QuestionInstrument.professional_types, order=993_001
    )

    response = await client.post(
        f"/api/v1/assessment/{assessment.id}/answers",
        json={"answers": [{"question_id": str(question.id), "value": 5}]},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "question_requires_pair_answer"
    assert await _stored_answers(db_session, assessment.id) == []
