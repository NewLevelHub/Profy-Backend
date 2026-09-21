"""PRO-338 Ф3.3 — astur_runs is append-only: `assessment_id` must NOT be
unique (a repeat run inserts a new row, never overwrites). No submit/scoring
endpoint exists yet (Ф3.4/Ф3.5) — this only proves the table/model shape
itself, same scope as the ticket ("Модель данных: astur_runs"). Also proves
the "raw data now, scores later" split: `answers`/`subtest_timings_ms`/
`lability_answers` default to `{}` (never NULL), while `raw_score`/
`spn_group`/lability accuracies stay `NULL` until a future scoring step."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.astur_run import AsturRun
from app.models.profile import AgeGroup, Profile
from app.models.user import User


async def _make_assessment(db: AsyncSession) -> tuple[Assessment, User]:
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


async def test_a_bare_run_defaults_raw_data_dicts_to_empty_not_null(db_session: AsyncSession) -> None:
    """Shape mirrors Ф3.4's per-subtest submit: a row can exist with nothing
    submitted yet (all JSONB dicts empty), before any subtest is answered."""
    assessment, user = await _make_assessment(db_session)

    run = AsturRun(assessment_id=assessment.id, user_id=user.id)
    db_session.add(run)
    await db_session.flush()

    fetched = (await db_session.execute(
        select(AsturRun).where(AsturRun.assessment_id == assessment.id)
    )).scalar_one()
    assert fetched.answers == {}
    assert fetched.subtest_timings_ms == {}
    assert fetched.lability_answers == {}
    assert fetched.subtest_scores == {}
    assert fetched.recommended_profile == {}
    # Scalar scoring fields stay NULL until a scoring step runs (Ф3.5) —
    # they have no meaningful "empty" value, unlike the JSONB containers.
    assert fetched.raw_score is None
    assert fetched.spn_group is None
    assert fetched.lability_first_half_accuracy is None
    assert fetched.lability_second_half_accuracy is None
    assert fetched.created_at is not None


async def test_a_fully_populated_run_can_be_inserted_and_read_back(db_session: AsyncSession) -> None:
    assessment, user = await _make_assessment(db_session)

    run = AsturRun(
        assessment_id=assessment.id, user_id=user.id,
        answers={"awareness": {"1": "жизнеописание"}, "analogies": {"1": "книги"}},
        subtest_timings_ms={"awareness": 480000, "analogies": 360000},
        lability_answers={"1": "1", "3": "плюс"},
        lability_first_half_accuracy=1.0,
        lability_second_half_accuracy=0.75,
        raw_score=62,
        subtest_scores={"awareness": 18, "analogies": 14, "classification": 10,
                        "generalization": 30, "logical_schemas": 20, "numeric_series": 12},
        spn_group=2,
        recommended_profile={"recommended": "natural_science",
                              "shares": {"humanities": 0.3, "physics_math": 0.2, "natural_science": 0.5}},
    )
    db_session.add(run)
    await db_session.flush()

    fetched = (await db_session.execute(
        select(AsturRun).where(AsturRun.assessment_id == assessment.id)
    )).scalar_one()
    assert fetched.raw_score == 62
    assert fetched.spn_group == 2
    assert fetched.subtest_scores["generalization"] == 30
    assert fetched.recommended_profile["recommended"] == "natural_science"
    assert fetched.lability_first_half_accuracy == 1.0
    assert fetched.lability_second_half_accuracy == 0.75


async def test_assessment_id_is_not_unique_repeat_runs_append(db_session: AsyncSession) -> None:
    assessment, user = await _make_assessment(db_session)

    db_session.add(AsturRun(assessment_id=assessment.id, user_id=user.id, raw_score=40))
    await db_session.flush()
    db_session.add(AsturRun(assessment_id=assessment.id, user_id=user.id, raw_score=55))
    await db_session.flush()

    rows = (await db_session.execute(
        select(AsturRun).where(AsturRun.assessment_id == assessment.id)
    )).scalars().all()
    assert len(rows) == 2  # both kept — no unique constraint collapsed them


async def test_deleting_the_assessment_cascades_to_its_astur_runs(db_session: AsyncSession) -> None:
    assessment, user = await _make_assessment(db_session)
    db_session.add(AsturRun(assessment_id=assessment.id, user_id=user.id, raw_score=40))
    await db_session.flush()

    await db_session.delete(assessment)
    await db_session.flush()

    rows = (await db_session.execute(
        select(AsturRun).where(AsturRun.assessment_id == assessment.id)
    )).scalars().all()
    assert rows == []
