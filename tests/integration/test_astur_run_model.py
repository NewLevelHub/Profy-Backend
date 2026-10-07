"""PRO-338 Ф3.3 / PRO-427 — astur_runs: append-only history per assessment,
raw-protocol dicts default to `{}`, frozen-result fields stay NULL until
finalize, every run is pinned to a bank version, and at most one attempt
per assessment is in progress."""
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.astur_run import AsturRun, AsturRunStatus
from tests.integration.astur_helpers import make_student, v1_version_id


async def test_a_bare_run_is_in_progress_with_empty_protocol_and_no_result(db_session: AsyncSession) -> None:
    user, assessment, _ = await make_student(db_session)
    db_session.add(AsturRun(assessment_id=assessment.id, user_id=user.id, bank_version_id=await v1_version_id(db_session)))
    await db_session.flush()

    run = (await db_session.execute(select(AsturRun).where(AsturRun.assessment_id == assessment.id))).scalar_one()
    assert run.status == AsturRunStatus.in_progress
    assert (run.answers, run.subtest_timings_ms, run.lability_answers) == ({}, {}, {})
    assert run.result_snapshot is None
    assert run.scoring_version is None
    assert run.completed_at is None


async def test_completed_runs_append_and_are_kept(db_session: AsyncSession) -> None:
    user, assessment, _ = await make_student(db_session)
    version_id = await v1_version_id(db_session)
    for _ in range(2):
        db_session.add(AsturRun(
            assessment_id=assessment.id, user_id=user.id, bank_version_id=version_id,
            status=AsturRunStatus.completed,
        ))
        await db_session.flush()

    rows = (await db_session.execute(select(AsturRun).where(AsturRun.assessment_id == assessment.id))).scalars().all()
    assert len(rows) == 2


async def test_only_one_attempt_can_be_in_progress(db_session: AsyncSession) -> None:
    user, assessment, _ = await make_student(db_session)
    version_id = await v1_version_id(db_session)
    db_session.add(AsturRun(assessment_id=assessment.id, user_id=user.id, bank_version_id=version_id))
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(AsturRun(assessment_id=assessment.id, user_id=user.id, bank_version_id=version_id))


async def test_deleting_the_assessment_cascades_to_its_astur_runs(db_session: AsyncSession) -> None:
    user, assessment, _ = await make_student(db_session)
    db_session.add(AsturRun(assessment_id=assessment.id, user_id=user.id, bank_version_id=await v1_version_id(db_session)))
    await db_session.flush()

    await db_session.delete(assessment)
    await db_session.flush()

    rows = (await db_session.execute(select(AsturRun).where(AsturRun.assessment_id == assessment.id))).scalars().all()
    assert rows == []
