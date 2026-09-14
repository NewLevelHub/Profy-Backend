"""Big Five retired from the active test pool (docs/big-five-retirement.md).

Runs against the shared dev DB (see tests/conftest.py / test_report_completion_
gate.py's module docstring) — real seeded content, rollback-isolated per test.
Confirms the query-layer exclusion (app.services.age_tiers.RETIRED_INSTRUMENTS)
actually stops Big Five from being served to new assessments, for every age
tier, without touching the underlying `Question`/`QuestionPair` rows (which
must stay in the DB — see scripts/seed_bigfive_questions.py's orphan-delete
caveat in the module this test exercises)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import AgeGroup
from app.models.question import Question, QuestionInstrument
from app.models.question_pair import QuestionPair
from app.services import question_pair_service, question_service


async def test_get_all_questions_never_serves_big_five_for_any_age_tier(
    db_session: AsyncSession,
) -> None:
    for age_group in (AgeGroup.junior, AgeGroup.middle, AgeGroup.senior):
        served = await question_service.get_all_questions(db_session, age_group)
        assert served, f"seeded question bank is missing rows for {age_group}"
        assert not any(q.instrument == QuestionInstrument.big_five for q in served), (
            f"{age_group} was served a Big Five question — active pool exclusion regressed"
        )


async def test_big_five_rows_still_exist_in_the_db_just_not_served(
    db_session: AsyncSession,
) -> None:
    """The exclusion must be query-layer only — no Question row is ever
    deleted (see plan: the self-healing seed script's orphan-delete would
    cascade-delete historical UserResponse rows if the bank were emptied
    instead of filtering at the query layer)."""
    total_big_five = (
        await db_session.execute(
            select(Question.id).where(Question.instrument == QuestionInstrument.big_five)
        )
    ).scalars().all()
    assert total_big_five, "Big Five Question rows must remain in the DB (historical data)"


async def test_junior_pairs_phase_is_entirely_retired(db_session: AsyncSession) -> None:
    pairs = await question_pair_service.get_pairs(db_session, AgeGroup.junior)
    assert pairs == []

    # The underlying junior-tier Big Five QuestionPair rows are untouched.
    junior_pairs_in_db = (
        await db_session.execute(
            select(QuestionPair.id).where(QuestionPair.age_tier == AgeGroup.junior)
        )
    ).scalars().all()
    assert junior_pairs_in_db, "junior QuestionPair rows must remain in the DB (historical data)"


async def test_middle_pairs_keep_riasec_but_lose_big_five(db_session: AsyncSession) -> None:
    pairs = await question_pair_service.get_pairs(db_session, AgeGroup.middle)
    assert pairs, "middle must still get its RIASEC dilemma pairs"
    assert not any(p.instrument == QuestionInstrument.big_five for p in pairs), (
        "middle's pairs screen must never serve Big Five"
    )


async def test_likert_total_matches_what_get_all_questions_actually_serves(
    db_session: AsyncSession,
) -> None:
    from app.services import assessment_shared

    for age_group in (AgeGroup.junior, AgeGroup.middle, AgeGroup.senior):
        served = await question_service.get_all_questions(db_session, age_group)
        total = await assessment_shared.likert_total_questions(db_session, age_group)
        assert total == len(served), (
            f"{age_group}: completion-gate denominator must match what's actually served"
        )
