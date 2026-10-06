"""Regression coverage for retiring Big Five from new assessments."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question, QuestionInstrument
from app.models.user_response import UserResponse
from app.services import (
    admin_service,
    assessment_service,
    assessment_shared,
    question_pair_service,
    question_service,
)
from tests.integration.astur_helpers import make_student


async def test_get_all_questions_never_serves_big_five(
    db_session: AsyncSession,
) -> None:
    served = await question_service.get_all_questions(db_session)

    assert served, "seeded question bank is missing active rows"
    assert not any(q.instrument == QuestionInstrument.big_five for q in served)


async def test_big_five_rows_remain_for_historical_reports(
    db_session: AsyncSession,
) -> None:
    stored = (
        await db_session.execute(
            select(Question.id).where(
                Question.instrument == QuestionInstrument.big_five
            )
        )
    ).scalars().all()

    assert stored, "Big Five rows must remain available for historical scoring"


async def test_pairs_never_serve_big_five(db_session: AsyncSession) -> None:
    pairs = await question_pair_service.get_pairs(db_session)

    assert pairs, "seeded DDO pair bank is missing rows"
    assert not any(p.instrument == QuestionInstrument.big_five for p in pairs)


async def test_likert_total_matches_the_served_question_pool(
    db_session: AsyncSession,
) -> None:
    served = await question_service.get_all_questions(db_session)
    total = await assessment_shared.likert_total_questions(db_session)

    assert total == len(served)


async def test_answers_endpoint_rejects_retired_big_five_atomically(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A stale pre-retirement client cannot mix Big Five rows into a new
    assessment. The whole batch is rejected before its valid rows are saved."""
    _user, assessment, headers = await make_student(db_session)
    active_id = (
        await db_session.execute(
            select(Question.id)
            .where(Question.instrument == QuestionInstrument.riasec)
            .limit(1)
        )
    ).scalar_one()
    retired_id = (
        await db_session.execute(
            select(Question.id)
            .where(Question.instrument == QuestionInstrument.big_five)
            .limit(1)
        )
    ).scalar_one()

    response = await client.post(
        f"/api/v1/assessment/{assessment.id}/answers",
        json={
            "answers": [
                {"question_id": str(active_id), "value": 4},
                {"question_id": str(retired_id), "value": 4},
            ]
        },
        headers=headers,
    )

    assert response.status_code == 400
    stored = (
        await db_session.execute(
            select(UserResponse).where(
                UserResponse.assessment_id == assessment.id
            )
        )
    ).scalars().all()
    assert stored == []


async def test_retired_answers_cannot_fill_a_missing_active_answer(
    db_session: AsyncSession,
) -> None:
    """Regression for PROFY-002's completion bypass: even a full legacy Big
    Five answer set cannot compensate for one missing current-battery row."""
    _user, assessment, _headers = await make_student(db_session)
    active_ids = list(
        (
            await db_session.execute(
                select(Question.id)
                .where(Question.instrument != QuestionInstrument.big_five)
                .order_by(Question.id)
            )
        ).scalars()
    )
    retired_ids = list(
        (
            await db_session.execute(
                select(Question.id).where(
                    Question.instrument == QuestionInstrument.big_five
                )
            )
        ).scalars()
    )
    assert active_ids and retired_ids

    db_session.add_all(
        [
            UserResponse(
                assessment_id=assessment.id,
                question_id=question_id,
                answer_value=4,
            )
            for question_id in [*active_ids[:-1], *retired_ids]
        ]
    )
    await db_session.flush()

    progress = await assessment_service.submit_answers(
        assessment.id, [], assessment.profile_id, db_session
    )

    assert progress.total == len(active_ids)
    assert progress.answered_count == len(active_ids) - 1
    assert progress.completed is False


async def test_admin_total_questions_excludes_big_five(
    db_session: AsyncSession,
) -> None:
    """The admin "answered N of M" counter must use the battery a student is
    actually served — counting the retired Big Five rows too showed a
    completed attempt as e.g. 365 of 485 (PRO-430 §3)."""
    user, assessment, _ = await make_student(db_session)
    active_id = (
        await db_session.execute(
            select(Question.id)
            .where(Question.instrument == QuestionInstrument.riasec)
            .limit(1)
        )
    ).scalar_one()
    retired_id = (
        await db_session.execute(
            select(Question.id)
            .where(Question.instrument == QuestionInstrument.big_five)
            .limit(1)
        )
    ).scalar_one()
    db_session.add_all(
        [
            UserResponse(
                assessment_id=assessment.id,
                question_id=active_id,
                answer_value=4,
            ),
            UserResponse(
                assessment_id=assessment.id,
                question_id=retired_id,
                answer_value=4,
            ),
        ]
    )
    await db_session.flush()
    served = len(await question_service.get_all_questions(db_session))

    assert await assessment_shared.likert_answered_count(
        assessment.id, db_session
    ) == 1
    saved = await assessment_service.get_saved_answers(
        assessment.id, assessment.profile_id, db_session
    )
    assert saved.question_values == {active_id: 4}

    user_detail = await admin_service.get_user_detail(db_session, user.id)
    assessment_detail = await admin_service.get_assessment_detail(db_session, assessment.id)

    assert [a.total_questions for a in user_detail.assessments] == [served]
    assert [a.answered_count for a in user_detail.assessments] == [1]
    assert assessment_detail.total_questions == served
    assert assessment_detail.answered_count == 1
    assert {response.instrument for response in assessment_detail.responses} >= {
        QuestionInstrument.riasec.value,
        QuestionInstrument.big_five.value,
    }
