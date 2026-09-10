"""PRO-299: protocol-validity scoring — the four spec fixtures
(psych-block-spec.md §A) plus the persistence / isolation contract.

  идеальный протокол  → green, not careless, low SD
  сплошные «3»        → careless via LongString + IRV + infrequency → red
  зигзаг              → high variance is NOT flagged careless
  провалены 2 ловушки → infrequency flag trips careless → red
"""
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import validity_thresholds
from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal
from app.models.assessment_validity import AssessmentValidity, SdLevel, TrafficLight
from app.models.profile import AgeGroup, Profile
from app.models.question import (
    BigFiveDomain,
    HollandType,
    Keyed,
    Question,
    QuestionInstrument,
    ValidityRole,
)
from app.models.user import User
from app.models.user_response import UserResponse
from app.models.validity_calibration_log import ValidityCalibrationLog
from app.services import validity_service

# psych-block-spec.md §A2 — 11 direct (keyed=agree), 9 reverse (keyed=disagree)
_DIRECT_ITEMS = {1, 2, 3, 4, 5, 8, 11, 14, 15, 16, 20}
_TRAP_EXPECTED = ["agree", "agree", "disagree", "disagree", "disagree"]  # infreq_01..05


async def _setup(
    db: AsyncSession, *, n_bigfive: int = 60, with_analysis: bool = False
) -> tuple[Assessment, list[Question], list[Question], list[Question]]:
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
    if with_analysis:
        db.add(AnalysisResult(assessment_id=assessment.id, summary="x"))
        await db.flush()

    await db.execute(
        delete(Question).where(Question.instrument == QuestionInstrument.validity)
    )

    base: list[Question] = []
    for i, holland in enumerate(list(HollandType)):
        q = Question(
            instrument=QuestionInstrument.riasec, riasec_type=holland,
            text=f"r{i}", order=1 + i, age_tier=AgeGroup.senior,
        )
        base.append(q)
        db.add(q)
    for i in range(n_bigfive):
        q = Question(
            instrument=QuestionInstrument.big_five,
            bigfive_domain=list(BigFiveDomain)[i % 5],
            keyed=Keyed.plus if i % 2 else Keyed.minus, facet=1,
            text=f"b{i}", order=100 + i, age_tier=AgeGroup.senior,
        )
        base.append(q)
        db.add(q)

    mc_sds: list[Question] = []
    for n in range(1, 21):
        keyed = "agree" if n in _DIRECT_ITEMS else "disagree"
        q = Question(
            instrument=QuestionInstrument.validity, validity_role=ValidityRole.sd_key,
            validity_meta={"key": f"mc_sds_{n:02d}", "keyed": keyed},
            text=f"mc {n}", order=300 + n, age_tier=AgeGroup.middle,
        )
        mc_sds.append(q)
        db.add(q)
    traps: list[Question] = []
    for i, expected in enumerate(_TRAP_EXPECTED, start=1):
        q = Question(
            instrument=QuestionInstrument.validity,
            validity_role=ValidityRole.infrequency,
            validity_meta={"key": f"infreq_{i:02d}", "expected_answer": expected},
            text=f"trap {i}", order=330 + i, age_tier=AgeGroup.middle,
        )
        traps.append(q)
        db.add(q)
    await db.flush()
    return assessment, base, mc_sds, traps


async def _answer(db: AsyncSession, assessment_id: uuid.UUID, pairs) -> None:
    for question, value in pairs:
        db.add(UserResponse(
            assessment_id=assessment_id, question_id=question.id, answer_value=value,
        ))
    await db.flush()


_HONEST_CYCLE = [2, 4, 3, 5, 3, 4, 2, 3]  # varied, no runs, IRV ~1.0


def _honest_base(base: list[Question]) -> list[tuple[Question, int]]:
    return [(q, _HONEST_CYCLE[i % len(_HONEST_CYCLE)]) for i, q in enumerate(base)]


# --------------------------------------------------------------------------
# The four spec fixtures
# --------------------------------------------------------------------------
async def test_clean_protocol_is_green(db_session: AsyncSession) -> None:
    assessment, base, mc_sds, traps = await _setup(db_session)
    pairs = _honest_base(base)
    # answer MC-SDS honestly-moderate → almost nothing scores
    for n, q in enumerate(mc_sds, start=1):
        pairs.append((q, 2 if n in _DIRECT_ITEMS else 4))
    for q, expected in zip(traps, _TRAP_EXPECTED):
        pairs.append((q, 5 if expected == "agree" else 1))  # pass every trap
    await _answer(db_session, assessment.id, pairs)

    result = await validity_service.compute(
        assessment.id, db_session, age_group=AgeGroup.senior
    )
    assert result.sd_level == SdLevel.ok
    assert result.careless_flag is False
    assert result.traffic_light == TrafficLight.green
    assert result.infrequency_failed == 0


async def test_all_threes_is_careless_red(db_session: AsyncSession) -> None:
    assessment, base, mc_sds, traps = await _setup(db_session)
    await _answer(
        db_session, assessment.id, [(q, 3) for q in (*base, *mc_sds, *traps)]
    )

    result = await validity_service.compute(
        assessment.id, db_session, age_group=AgeGroup.senior
    )
    assert result.sd_raw == 0  # "3" folds to neither pole
    assert result.longstring_max >= validity_thresholds.longstring_max_flag
    assert result.irv == 0.0
    assert result.infrequency_failed == len(traps)  # a "3" fails every trap
    assert result.careless_flag is True
    assert result.traffic_light == TrafficLight.red
    reasons = result.details["careless_reasons"]
    assert reasons["longstring"] and reasons["irv_low"] and reasons["infrequency"]


async def test_zigzag_high_variance_is_not_careless(db_session: AsyncSession) -> None:
    assessment, base, mc_sds, traps = await _setup(db_session)
    pairs = [(q, 1 if i % 2 else 5) for i, q in enumerate((*base, *mc_sds))]
    for q, expected in zip(traps, _TRAP_EXPECTED):
        pairs.append((q, 5 if expected == "agree" else 1))  # pass every trap
    await _answer(db_session, assessment.id, pairs)

    result = await validity_service.compute(
        assessment.id, db_session, age_group=AgeGroup.senior
    )
    assert result.longstring_max < validity_thresholds.longstring_max_flag
    assert result.irv > 1.0
    assert result.infrequency_failed == 0
    assert result.careless_flag is False


async def test_two_failed_traps_trips_careless_red(db_session: AsyncSession) -> None:
    assessment, base, mc_sds, traps = await _setup(db_session)
    pairs = _honest_base(base)
    for n, q in enumerate(mc_sds, start=1):
        pairs.append((q, 2 if n in _DIRECT_ITEMS else 4))
    # fail exactly 2 of the 5 traps (answer opposite the expected pole)
    for idx, (q, expected) in enumerate(zip(traps, _TRAP_EXPECTED)):
        passing = 5 if expected == "agree" else 1
        failing = 1 if expected == "agree" else 5
        pairs.append((q, failing if idx < 2 else passing))
    await _answer(db_session, assessment.id, pairs)

    result = await validity_service.compute(
        assessment.id, db_session, age_group=AgeGroup.senior
    )
    assert result.infrequency_failed == 2
    assert result.careless_flag is True
    assert result.traffic_light == TrafficLight.red
    failed = [it for it in result.details["infrequency_items"] if it["failed"]]
    assert len(failed) == 2


# --------------------------------------------------------------------------
# Acceptance criteria
# --------------------------------------------------------------------------
def _mc_sds_answers(keyed_count: int) -> list[int]:
    """Answers for the 20 MC-SDS items (index 0 = item 1) that score exactly
    `keyed_count` points: the first `keyed_count` items answered in their
    keyed (socially-desirable) direction, the rest against it."""
    out: list[int] = []
    for n in range(1, 21):
        keyed_dir = 5 if n in _DIRECT_ITEMS else 1
        against = 1 if n in _DIRECT_ITEMS else 5
        out.append(keyed_dir if n <= keyed_count else against)
    return out


async def test_social_desirability_band_stays_green(db_session: AsyncSession) -> None:
    """9–15 (`social_desirability`) is normative adolescent conformity — it
    raises no flag, only shows in the breakdown (psych-block-spec.md §A5).
    Corrected from the earlier '§A4 table' reading that made it yellow."""
    assessment, base, mc_sds, traps = await _setup(db_session)
    pairs = _honest_base(base)
    for q, value in zip(mc_sds, _mc_sds_answers(12)):
        pairs.append((q, value))
    for q, expected in zip(traps, _TRAP_EXPECTED):
        pairs.append((q, 5 if expected == "agree" else 1))
    await _answer(db_session, assessment.id, pairs)

    result = await validity_service.compute(
        assessment.id, db_session, age_group=AgeGroup.senior
    )
    assert result.sd_raw == 12
    assert result.sd_level == SdLevel.social_desirability
    assert result.careless_flag is False
    assert result.traffic_light == TrafficLight.green


async def test_high_sd_band_is_yellow(db_session: AsyncSession) -> None:
    assessment, base, mc_sds, traps = await _setup(db_session)
    pairs = _honest_base(base)
    for q, value in zip(mc_sds, _mc_sds_answers(18)):
        pairs.append((q, value))
    for q, expected in zip(traps, _TRAP_EXPECTED):
        pairs.append((q, 5 if expected == "agree" else 1))
    await _answer(db_session, assessment.id, pairs)

    result = await validity_service.compute(
        assessment.id, db_session, age_group=AgeGroup.senior
    )
    assert result.sd_raw == 18
    assert result.sd_level == SdLevel.high
    assert result.careless_flag is False
    assert result.traffic_light == TrafficLight.yellow  # sd_raw >= 16 only


async def test_carelessness_outranks_social_desirability(db_session: AsyncSession) -> None:
    """A protocol that is BOTH faked-good (sd_raw high) AND careless is `red`,
    not `yellow` (psych-block-spec.md §A5)."""
    assessment, base, mc_sds, traps = await _setup(db_session)
    pairs = _honest_base(base)
    # answer every MC-SDS item in its keyed (socially-desirable) direction → sd_raw = 20
    for n, q in enumerate(mc_sds, start=1):
        pairs.append((q, 5 if n in _DIRECT_ITEMS else 1))
    for q in traps:  # fail all traps → carelessness
        pairs.append((q, 3))
    await _answer(db_session, assessment.id, pairs)

    result = await validity_service.compute(
        assessment.id, db_session, age_group=AgeGroup.senior
    )
    assert result.sd_raw == 20 and result.sd_level == SdLevel.high
    assert result.careless_flag is True
    assert result.traffic_light == TrafficLight.red  # carelessness wins


async def test_score_and_store_persists_every_metric(db_session: AsyncSession) -> None:
    assessment, base, mc_sds, traps = await _setup(db_session, with_analysis=True)
    pairs = _honest_base(base)
    for n, q in enumerate(mc_sds, start=1):
        pairs.append((q, 2 if n in _DIRECT_ITEMS else 4))
    for q, expected in zip(traps, _TRAP_EXPECTED):
        pairs.append((q, 5 if expected == "agree" else 1))
    await _answer(db_session, assessment.id, pairs)

    result = await validity_service.score_and_store(
        assessment.id, db_session, age_group=AgeGroup.senior
    )

    row = (await db_session.execute(
        select(AssessmentValidity).where(
            AssessmentValidity.assessment_id == assessment.id
        )
    )).scalar_one()
    assert row.sd_raw == result.sd_raw
    assert row.sd_level == result.sd_level
    assert row.traffic_light == result.traffic_light
    assert row.longstring_max == result.longstring_max
    assert row.infrequency_failed == result.infrequency_failed
    assert row.thresholds_version == validity_thresholds.version
    # rt_ms is stored (passive Δt); this test's answers are all one flush →
    # identical created_at → all-zero deltas, but the key is present.
    assert "deltas_ms" in row.rt_ms
    assert all(delta == 0 for delta in row.rt_ms["deltas_ms"])
    assert row.details["d2_mahalanobis"] is None

    analysis = (await db_session.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment.id)
    )).scalar_one()
    assert analysis.validity["traffic_light"] == result.traffic_light.value
    assert analysis.validity["thresholds_version"] == validity_thresholds.version


async def test_calibration_log_appends_one_row_per_run(db_session: AsyncSession) -> None:
    assessment, base, mc_sds, traps = await _setup(db_session)
    await _answer(
        db_session, assessment.id,
        [(q, 4) for q in (*base, *mc_sds, *traps)],
    )

    await validity_service.score_and_store(assessment.id, db_session, age_group=AgeGroup.senior)
    await validity_service.score_and_store(assessment.id, db_session, age_group=AgeGroup.senior)

    rows = (await db_session.execute(
        select(ValidityCalibrationLog).where(
            ValidityCalibrationLog.assessment_id == assessment.id
        )
    )).scalars().all()
    assert len(rows) == 2  # retake appends, does not overwrite
    assert all(r.age_group == AgeGroup.senior for r in rows)
    assert all(r.thresholds_version == validity_thresholds.version for r in rows)


async def test_d2_mahalanobis_is_an_explicit_stub() -> None:
    assert validity_service._d2_mahalanobis() is None


async def test_score_and_store_overwrites_a_previous_verdict(
    db_session: AsyncSession,
) -> None:
    """A retake re-runs `score_and_store`; `assessment_validity` is unique on
    `assessment_id`, so the row is updated in place, not duplicated."""
    assessment, base, mc_sds, traps = await _setup(db_session)

    # a stale verdict from an earlier run
    db_session.add(AssessmentValidity(
        assessment_id=assessment.id, sd_raw=20, sd_level=SdLevel.high,
        longstring_max=99, irv=0.0, infrequency_failed=5, careless_flag=True,
        traffic_light=TrafficLight.red, thresholds_version=1,
    ))
    await db_session.flush()

    # score a clean protocol now
    pairs = _honest_base(base)
    for n, q in enumerate(mc_sds, start=1):
        pairs.append((q, 2 if n in _DIRECT_ITEMS else 4))
    for q, expected in zip(traps, _TRAP_EXPECTED):
        pairs.append((q, 5 if expected == "agree" else 1))
    await _answer(db_session, assessment.id, pairs)

    result = await validity_service.score_and_store(
        assessment.id, db_session, age_group=AgeGroup.senior
    )

    rows = (await db_session.execute(
        select(AssessmentValidity).where(
            AssessmentValidity.assessment_id == assessment.id
        )
    )).scalars().all()
    assert len(rows) == 1  # updated in place, not duplicated
    assert rows[0].traffic_light == result.traffic_light == TrafficLight.green
    assert rows[0].sd_raw == result.sd_raw
    assert rows[0].careless_flag is False
