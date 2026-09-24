"""Regression coverage for retiring Big Five from new assessments."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question, QuestionInstrument
from app.services import assessment_shared, question_pair_service, question_service


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
