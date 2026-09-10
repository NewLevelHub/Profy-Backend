"""PRO-291 positive invariant: /result carries the validity / psychoemotional
/ mac sections after a completed assessment, and the main RIASEC/BigFive/MI
report still comes back even when a psych-block calculation is forced to blow
up. This is NOT a "does not leak" guard (PRO-282 §3 explicitly wants the
sections visible in the MVP) — it's the isolation + wiring contract.

LLM is monkeypatched off explicitly (same reasoning as
test_result_v2_fallback.py: this dev env has a working key).
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.assessment_validity import AssessmentValidity
from app.models.profile import AgeGroup, Profile
from app.models.psychoemotional_run import PsychoEmotionalRun, PsychoEmotionalValidityFlag
from app.models.user import User
from app.models.validity_calibration_log import ValidityCalibrationLog
from app.schemas.result_v2 import ResultResponseV2, ValiditySection
from app.services import (
    assessment_shared,
    consent_service,
    llm_client,
    motivation_pair_service,
    motivation_service,
    report_service,
    validity_service,
)
from app.services.psychoemotional import engine
from app.services.psychoemotional import scoring as psychoemotional_scoring


async def _make_assessment(db_session: AsyncSession, age_group: AgeGroup) -> tuple[User, Assessment]:
    user = User(
        email=f"{uuid.uuid4()}@example.com", hashed_password="x", is_active=True, is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    profile = Profile(
        user_id=user.id, name="Тест", age={AgeGroup.junior: 8, AgeGroup.senior: 16}[age_group],
        grade=5, city="Алматы", country="Казахстан", language="ru", age_group=age_group,
    )
    db_session.add(profile)
    await db_session.flush()

    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db_session.add(assessment)
    await db_session.flush()
    return user, assessment


def _validity_section(**overrides) -> ValiditySection:
    """A fully-populated ValiditySection for stub builders (PRO-300 made the
    verdict fields required)."""
    return ValiditySection(**{
        "consent_ok": False,
        "traffic_light": "green",
        "sd_raw": 4,
        "sd_level": "ok",
        "sd_bounds": (8, 15),
        "longstring_max": 3,
        "irv": 1.2,
        "infrequency_failed": 0,
        "careless_flag": False,
        "thresholds_version": 2,
        **overrides,
    })


def _force_complete_and_llm_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assessment_shared, "likert_answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "likert_total_questions", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "total_triplets", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_pair_service, "answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_pair_service, "total_pairs", AsyncMock(return_value=1))
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)


async def test_result_carries_the_three_psych_sections(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch)

    response = await report_service.build_report(assessment.id, db_session, viewer=user)

    dumped = response.model_dump()
    for section in ("validity", "psychoemotional", "mac"):
        assert section in dumped
    # validity is computed at report time now (PRO-299); psychoemotional / mac
    # stay `null` until their phases ship.
    assert dumped["validity"] is not None
    assert dumped["psychoemotional"] is None
    assert dumped["mac"] is None


async def test_main_report_survives_a_broken_psych_block_calculation(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch)

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("psychoemotional scoring blew up")

    monkeypatch.setattr(report_service, "_build_psychoemotional_section", _boom)

    response = await report_service.build_report(assessment.id, db_session, viewer=user)

    assert isinstance(response, ResultResponseV2)
    assert response.summary  # main report fully intact
    assert response.interest_instrument == "riasec"
    assert len(response.interest_map) == 6
    assert response.psychoemotional is None  # broken block degraded to null
    assert response.mac is None
    # validity is computed independently of the psychoemotional builder — a
    # crash in one section does not suppress another.
    assert response.validity is not None


async def test_psych_sections_for_is_the_single_visibility_switch(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch)

    async def _stub_validity(*_args, **kwargs):
        return _validity_section(consent_ok=kwargs.get("consent_ok", False))

    monkeypatch.setattr(report_service, "_build_validity_section", _stub_validity)

    on = await report_service.build_report(assessment.id, db_session, viewer=user)
    assert on.validity is not None

    # Flip the one resolver → section withheld, main report still returned.
    # No cache-bust needed: the base report is cached, psych sections are
    # re-attached on every call.
    monkeypatch.setattr(report_service, "psych_sections_for", lambda *a, **k: False)
    off = await report_service.build_report(assessment.id, db_session, viewer=user)
    assert off.summary
    assert off.validity is None


async def test_validity_section_is_built_from_the_assessment_validity_row(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PRO-297 wiring + PRO-299 trigger + PRO-300 shape: generating the report
    computes the `assessment_validity` row, and `_build_validity_section` (the
    real one, not a stub) surfaces the full verdict from it."""
    from app.config import validity_thresholds

    user, assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch)

    response = await report_service.build_report(assessment.id, db_session, viewer=user)

    section = response.validity
    assert section is not None
    assert section.thresholds_version == validity_thresholds.version
    assert section.consent_ok is False
    assert section.traffic_light in ("green", "yellow", "red")
    assert section.sd_level in ("ok", "social_desirability", "high")
    assert 0 <= section.sd_raw <= 20
    assert tuple(section.sd_bounds) == tuple(validity_thresholds.sd_bounds)
    assert section.longstring_max >= 0
    assert isinstance(section.careless_flag, bool)
    assert response.summary  # main report untouched

    row = (await db_session.execute(
        select(AssessmentValidity).where(
            AssessmentValidity.assessment_id == assessment.id
        )
    )).scalar_one()
    assert row.thresholds_version == validity_thresholds.version


async def test_consent_ok_flows_from_a_recorded_consent(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch)

    async def _echo_consent(_assessment_id, _db, *, consent_ok):
        return _validity_section(consent_ok=consent_ok)

    monkeypatch.setattr(report_service, "_build_validity_section", _echo_consent)

    before = await report_service.build_report(assessment.id, db_session, viewer=user)
    assert before.validity is not None and before.validity.consent_ok is False

    await consent_service.record_consent(
        db_session, user_id=user.id, signed_by="Родитель", assessment_id=assessment.id
    )
    after = await report_service.build_report(assessment.id, db_session, viewer=user)
    assert after.validity is not None and after.validity.consent_ok is True


async def test_generating_the_report_computes_and_stores_the_validity_verdict(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PRO-299 trigger: building the report for the first time runs
    validity_service, landing an `assessment_validity` row + one
    `validity_calibration_log` row."""
    user, assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch)

    await report_service.build_report(assessment.id, db_session, viewer=user)

    verdict = (await db_session.execute(
        select(AssessmentValidity).where(
            AssessmentValidity.assessment_id == assessment.id
        )
    )).scalar_one_or_none()
    assert verdict is not None
    assert verdict.thresholds_version is not None

    calib = (await db_session.execute(
        select(ValidityCalibrationLog).where(
            ValidityCalibrationLog.assessment_id == assessment.id
        )
    )).scalars().all()
    assert len(calib) == 1
    assert calib[0].age_group == AgeGroup.senior


async def test_main_report_survives_a_validity_scoring_exception(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch)

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("validity scoring blew up")

    monkeypatch.setattr(validity_service, "score_and_store", _boom)

    response = await report_service.build_report(assessment.id, db_session, viewer=user)

    assert isinstance(response, ResultResponseV2)
    assert response.summary  # main report fully intact
    assert response.interest_instrument == "riasec"
    # scoring failed → no assessment_validity row → section stays null
    assert response.validity is None


_PE_L1 = [4, 3, 2, 1, 5, 6, 0, 7]
_PE_L2 = [3, 4, 2, 0, 1, 5, 6, 7]  # §5.8 Аружан — SO 6, D 8, split 2


def _psychoemotional_run(assessment_id, user_id, **overrides) -> PsychoEmotionalRun:
    # `metrics` non-empty by default (real engine output for the seeded lists) →
    # the PRO-307 scoring trigger treats it as already-scored and leaves it
    # alone, and _build_psychoemotional_section (PRO-309) has a full row to
    # render. Pass `metrics={}` for a raw (unscored) run.
    l1 = overrides.get("list1", _PE_L1)
    l2 = overrides.get("list2", _PE_L2)
    return PsychoEmotionalRun(**{
        "assessment_id": assessment_id,
        "user_id": user_id,
        "list1": l1,
        "list2": l2,
        "pause_actual_sec": 130,
        "metrics": engine.compute(l1, l2).as_dict(),
        "validity_flag": PsychoEmotionalValidityFlag.ok,
        "thresholds_version": 1,
        **overrides,
    })


async def test_psychoemotional_section_is_built_from_the_latest_run(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PRO-305: no run → section null; a run → section carries
    `thresholds_version` + `validity_flag`; a second run does NOT overwrite —
    the section reflects the newest row."""
    user, assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch)

    before = await report_service.build_report(assessment.id, db_session, viewer=user)
    assert before.psychoemotional is None

    db_session.add(_psychoemotional_run(
        assessment.id, user.id, thresholds_version=1,
        validity_flag=PsychoEmotionalValidityFlag.caution,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    ))
    await db_session.flush()

    after = await report_service.build_report(assessment.id, db_session, viewer=user)
    assert after.psychoemotional is not None
    assert after.psychoemotional.thresholds_version == 1
    assert after.psychoemotional.validity_flag == "caution"
    assert after.summary  # main report untouched

    # retake → new row, older one kept
    db_session.add(_psychoemotional_run(
        assessment.id, user.id, thresholds_version=2,
        validity_flag=PsychoEmotionalValidityFlag.ok,
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    ))
    await db_session.flush()

    rows = (await db_session.execute(
        select(PsychoEmotionalRun).where(
            PsychoEmotionalRun.assessment_id == assessment.id
        )
    )).scalars().all()
    assert len(rows) == 2  # append-only history

    latest = await report_service.build_report(assessment.id, db_session, viewer=user)
    assert latest.psychoemotional.thresholds_version == 2
    assert latest.psychoemotional.validity_flag == "ok"


async def test_psychoemotional_section_carries_the_full_b8_composition(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PRO-309: секция отдаёт весь состав §B8 по последней строке — списки 1/2 +
    D, функц. пары с ( )/[ ], индексы с уровнями и раскладками, структурные
    без уровней, check-in, тексты-подсказки, thresholds_version."""
    user, assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch)

    db_session.add(_psychoemotional_run(
        assessment.id, user.id,
        checkin={"q1": "спокойно", "q2": "да", "q3": "обычно"},
        hint_keys=["fn.plus.3", "fn.minus.7"],
        validity_flag=PsychoEmotionalValidityFlag.ok,
        validity_reasons=[],
    ))
    await db_session.flush()

    section = (
        await report_service.build_report(assessment.id, db_session, viewer=user)
    ).psychoemotional
    assert section is not None

    assert section.run_number == 1
    assert section.history == []
    assert section.checkin == {"q1": "спокойно", "q2": "да", "q3": "обычно"}

    assert section.choice_1 == _PE_L1
    assert section.choice_2 == _PE_L2
    assert section.d_value == 8 and section.d_memory is False

    # §5.8 Аружан: +(3,4) ×(2,0) =(1,5) −(6,7), корневой конфликт 3/7
    assert [(p.sign, list(p.colors)) for p in section.positional_pairs] == [
        ("plus", [3, 4]), ("cross", [2, 0]), ("equal", [1, 5]), ("minus", [6, 7]),
    ]
    assert section.root_conflict == (3, 7)
    assert len(section.split_pairs) == 4
    assert section.split_count == 2 and section.instability is False

    assert section.anxiety.score == 0 and section.anxiety.level == "low"
    assert set(section.anxiety.breakdown) == {"1", "2", "3", "4"}
    assert section.compensation.score == 0
    assert section.compensation.purple_forward is False
    assert section.so_value == 6 and section.so_level == "norm"
    assert section.vk_value == 1.5 and section.vk_level == "balance"

    # структурные — только значения, без уровней
    assert section.structural.performance == sum(
        _PE_L2.index(c) + 1 for c in (2, 3, 4)
    )
    assert not hasattr(section.structural, "level")

    assert section.black_first is False
    assert section.thresholds_version == 1
    assert len(section.hints) == 2  # обе fn.* подсказки резолвнулись в текст
    assert all(isinstance(h, str) and h for h in section.hints)


async def test_psychoemotional_section_shows_previous_runs_as_dynamics(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PRO-309: динамика — компактный список прошлых прохождений (СО, тревога,
    флаг), новые сверху; секция всегда по последнему."""
    user, assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch)

    db_session.add(_psychoemotional_run(
        assessment.id, user.id,
        validity_flag=PsychoEmotionalValidityFlag.caution,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    ))
    db_session.add(_psychoemotional_run(
        assessment.id, user.id,
        list2=[0, 7, 6, 3, 5, 1, 2, 4],  # контраст — SO высокий, тревога 6
        validity_flag=PsychoEmotionalValidityFlag.ok,
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    ))
    await db_session.flush()

    section = (
        await report_service.build_report(assessment.id, db_session, viewer=user)
    ).psychoemotional
    assert section is not None
    assert section.run_number == 2
    assert section.so_level == "high"  # секция = последнее прохождение
    assert len(section.history) == 1

    prev = section.history[0]
    assert prev.run_number == 1
    assert prev.so == 6  # §5.8 Аружан
    assert prev.anxiety_score == 0
    assert prev.validity_flag == "caution"
    assert prev.completed_at == datetime(2026, 1, 1, tzinfo=timezone.utc)


async def test_report_generation_scores_the_latest_raw_psychoemotional_run(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PRO-307 trigger: a raw run (`metrics={}`) is scored on report
    generation — metrics + hint_keys land on the row, a compact summary on
    AnalysisResult.psychoemotional, thresholds_version stamped."""
    from app.config import psychoemotional_thresholds
    from app.models.analysis_result import AnalysisResult

    user, assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch)

    db_session.add(_psychoemotional_run(assessment.id, user.id, metrics={}))
    await db_session.flush()

    response = await report_service.build_report(assessment.id, db_session, viewer=user)

    run = (await db_session.execute(
        select(PsychoEmotionalRun).where(
            PsychoEmotionalRun.assessment_id == assessment.id
        )
    )).scalar_one()
    assert run.metrics != {}
    assert run.metrics["so"]["value"] == 6  # §5.8 Аружан
    assert run.hint_keys  # непусто
    assert run.thresholds_version == psychoemotional_thresholds.version

    analysis = (await db_session.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment.id)
    )).scalar_one()
    assert analysis.psychoemotional["so"] == 6
    assert analysis.psychoemotional["thresholds_version"] == psychoemotional_thresholds.version

    assert response.psychoemotional is not None
    assert response.psychoemotional.thresholds_version == psychoemotional_thresholds.version
    assert response.summary  # main report intact


async def test_report_generation_stores_and_serves_a_low_validity_flag(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PRO-308: a raw run that trips 2+ behavioural signs (§B7) is scored on
    report generation → `validity_flag='low'` + `validity_reasons` land on the
    row, and the run is still saved and surfaced in the /result section (реш. 10
    — a low flag never blocks or hides the run)."""
    user, assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch)

    # список 2 == список 1 → D = 0 (identical_lists); пауза 10 с < 120 (pause_not_held).
    db_session.add(_psychoemotional_run(
        assessment.id, user.id,
        metrics={},
        list1=[4, 3, 2, 1, 5, 6, 0, 7],
        list2=[4, 3, 2, 1, 5, 6, 0, 7],
        pause_actual_sec=10,
        validity_flag=None,
    ))
    await db_session.flush()

    response = await report_service.build_report(assessment.id, db_session, viewer=user)

    run = (await db_session.execute(
        select(PsychoEmotionalRun).where(
            PsychoEmotionalRun.assessment_id == assessment.id
        )
    )).scalar_one()
    assert run.validity_flag == PsychoEmotionalValidityFlag.low
    assert set(run.validity_reasons) == {"identical_lists", "pause_not_held"}
    assert run.metrics != {}  # прохождение сохранено и посчитано, не отброшено

    assert response.psychoemotional is not None
    assert response.psychoemotional.validity_flag == "low"
    assert set(response.psychoemotional.validity_reasons) == {
        "identical_lists", "pause_not_held"
    }
    assert response.summary  # основной отчёт цел


async def test_main_report_survives_a_psychoemotional_engine_exception(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, assessment = await _make_assessment(db_session, AgeGroup.senior)
    _force_complete_and_llm_disabled(monkeypatch)

    db_session.add(_psychoemotional_run(assessment.id, user.id, metrics={}))
    await db_session.flush()

    async def _boom(*_a, **_k):
        raise RuntimeError("МЦВ engine blew up")

    monkeypatch.setattr(psychoemotional_scoring, "score_and_store", _boom)

    response = await report_service.build_report(assessment.id, db_session, viewer=user)

    assert isinstance(response, ResultResponseV2)
    assert response.summary
    assert response.interest_instrument == "riasec"
