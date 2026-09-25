"""PRO-338 Ф0.2 — assembles NewTestsSections (app/schemas/new_tests.py) from
an AnalysisResult's specialist-only containers.

Each `_build_<x>_section` is isolated in its own try/except: a malformed or
partial JSONB container for one test must never blank the other 5 sections,
same isolation principle as PRO-291/299's `report_service._build_validity_
section` and neighbors. Consumed by Ф0.3's specialist report endpoint
(GET /psychologist/students/{id}/assessments/{assessment_id}/report), never
by the student-facing /result.
"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n.catalog import key as i18n_key
from app.models.analysis_result import AnalysisResult
from app.schemas.new_tests import (
    AspirationLevelSection,
    EmpathyConfidenceSection,
    IntelligenceSection,
    NewTestsSections,
    ProfessionalTypesSection,
    TeamRoleSection,
    TemperamentSection,
)
from app.schemas.astur import AsturResultSnapshot
from app.services import (
    belbin_service,
    boyko_empathy_service,
    elers_service,
    eysenck_service,
    kondash_anxiety_service,
    professional_types_service,
)
from app.services.astur import runs as astur_runs

logger = logging.getLogger(__name__)

# Ф2.7 / epic decision table §2: Belbin's source is 18+/corporate-context —
# a methodical note for the specialist, never a code-gated restriction (the
# platform's own age range, 14-18, is otherwise unaffected — see
# 00-ЭПИК-PRO-338.md's "Возраст" row).
_BELBIN_METHODOLOGICAL_NOTE = (
    i18n_key("report_copy", "belbin_methodological_note", locale="ru")
)


async def _build_professional_types_section(
    analysis_result: AnalysisResult, *, assessment_id: uuid.UUID, db: AsyncSession
) -> ProfessionalTypesSection | None:
    """ДДО — scored in Ф1 (02-Фаза1-Лёгкие-тесты.md); `None` until that
    service writes AnalysisResult.professional_types.

    `interest_scores`/`abilities_scores` are the pre-computed aggregates
    already persisted on `analysis_result`; `*_evidence` (the "Почему такой
    результат" real-answers breakdown) is computed live from `UserResponse`
    here instead, same "compute on read" choice as team_role/intelligence
    below — the raw answers were never worth persisting a second time
    alongside their own aggregate."""
    try:
        data = analysis_result.professional_types
        if not data:
            return None
        return ProfessionalTypesSection(
            **data,
            interest_evidence=await professional_types_service.interest_evidence(assessment_id, db),
            abilities_evidence=await professional_types_service.abilities_evidence(assessment_id, db),
        )
    except Exception:
        logger.exception(
            "Failed to build professional_types section for analysis_result %s", analysis_result.id
        )
        return None


async def _build_team_role_section(
    assessment_id: uuid.UUID, db: AsyncSession
) -> TeamRoleSection | None:
    """Belbin (Ф2.7). Unlike every other section here, its source is NOT an
    `AnalysisResult` JSONB column — `belbin_runs` (Ф2.3) is a separate
    append-only table (optional psychologist-assigned block, not part of
    the main battery/build_report() flow), so this builder is the one
    exception that takes `assessment_id`/`db` instead of `analysis_result`.
    `None` if Belbin was never assigned/completed for this assessment."""
    try:
        run = await belbin_service.get_latest_run(assessment_id, db)
        if run is None:
            return None
        interpretation = belbin_service.interpret_role_totals(run.role_totals)
        return TeamRoleSection(
            scores=run.role_totals,
            ranked_roles=interpretation.ranked_roles,
            dominant_role=interpretation.dominant_role,
            supporting_roles=interpretation.supporting_roles,
            avoidance_roles=interpretation.avoidance_roles,
            methodological_note=_BELBIN_METHODOLOGICAL_NOTE,
            role_evidence=await belbin_service.role_evidence(db, run),
        )
    except Exception:
        logger.exception("Failed to build team_role section for assessment %s", assessment_id)
        return None


async def _build_temperament_section(
    analysis_result: AnalysisResult, *, assessment_id: uuid.UUID, db: AsyncSession
) -> TemperamentSection | None:
    """Eysenck — scored in Ф1; `None` until that service writes
    AnalysisResult.eysenck. `*_evidence` (real Да/Нет answers per scale) is
    computed live from `UserResponse`, same reasoning as professional_types
    above."""
    try:
        data = analysis_result.eysenck
        if not data:
            return None
        evidence = await eysenck_service.answer_evidence(assessment_id, db) or {}
        return TemperamentSection(
            **data,
            extraversion_evidence=evidence.get("extraversion"),
            neuroticism_evidence=evidence.get("neuroticism"),
            lie_scale_evidence=evidence.get("lie"),
        )
    except Exception:
        logger.exception("Failed to build temperament section for analysis_result %s", analysis_result.id)
        return None


async def _build_intelligence_section(
    assessment_id: uuid.UUID, db: AsyncSession
) -> IntelligenceSection | None:
    """АСТУР (PRO-427): the snapshot frozen when the latest completed
    attempt was finalized — scoring never runs here, so a new bank version
    or formula can't change a result someone already read. `None` when no
    attempt has been completed (an open attempt alone has no result)."""
    try:
        run = await astur_runs.latest_completed_run(db, assessment_id)
        if run is None:
            return None
        if run.result_snapshot is None:
            logger.warning(
                "АСТУР run %s is completed but has no snapshot — run scripts/backfill_astur_legacy_snapshots.py",
                run.id,
            )
            return None
        snapshot = AsturResultSnapshot.model_validate(run.result_snapshot)
        return IntelligenceSection(
            run_id=run.id,
            retake_in_progress=await astur_runs.active_run(db, assessment_id) is not None,
            **snapshot.model_dump(exclude={"item_scores", "item_status"}),
        )
    except Exception:
        logger.exception("Failed to build intelligence section for assessment %s", assessment_id)
        return None


async def _build_aspiration_level_section(
    analysis_result: AnalysisResult, *, assessment_id: uuid.UUID, db: AsyncSession
) -> AspirationLevelSection | None:
    """Elers — scored in Ф1; `None` until that service writes
    AnalysisResult.elers. `evidence` (real Да/Нет answers) is computed live
    from `UserResponse`, same reasoning as professional_types above."""
    try:
        data = analysis_result.elers
        if not data:
            return None
        return AspirationLevelSection(
            **data,
            evidence=await elers_service.answer_evidence(assessment_id, db),
        )
    except Exception:
        logger.exception("Failed to build aspiration_level section for analysis_result %s", analysis_result.id)
        return None


async def _build_empathy_confidence_section(
    analysis_result: AnalysisResult, *, assessment_id: uuid.UUID, db: AsyncSession
) -> EmpathyConfidenceSection | None:
    """Бойко + Кондаш/Прихожан — scored in Ф1; `None` until that service
    writes AnalysisResult.empathy_confidence. `empathy_evidence`/
    `confidence_evidence` (real answers behind each instrument's half of
    this merged section) are computed live from `UserResponse`, same
    reasoning as professional_types above."""
    try:
        data = analysis_result.empathy_confidence
        if not data:
            return None
        return EmpathyConfidenceSection(
            **data,
            empathy_evidence=await boyko_empathy_service.answer_evidence(assessment_id, db),
            confidence_evidence=await kondash_anxiety_service.answer_evidence(assessment_id, db),
        )
    except Exception:
        logger.exception(
            "Failed to build empathy_confidence section for analysis_result %s", analysis_result.id
        )
        return None


async def build_new_tests_sections(
    analysis_result: AnalysisResult, *, assessment_id: uuid.UUID, db: AsyncSession
) -> NewTestsSections:
    """Always succeeds, never raises — every field independently falls back
    to None on its own builder's failure (see module docstring). Async
    (since Ф2.7) only because team_role's source is a separate table, not
    an `analysis_result` column — every other builder here stays a plain
    sync function on `analysis_result` alone."""
    return NewTestsSections(
        professional_types=await _build_professional_types_section(
            analysis_result, assessment_id=assessment_id, db=db
        ),
        team_role=await _build_team_role_section(assessment_id, db),
        temperament=await _build_temperament_section(analysis_result, assessment_id=assessment_id, db=db),
        intelligence=await _build_intelligence_section(assessment_id, db),
        aspiration_level=await _build_aspiration_level_section(
            analysis_result, assessment_id=assessment_id, db=db
        ),
        empathy_confidence=await _build_empathy_confidence_section(
            analysis_result, assessment_id=assessment_id, db=db
        ),
    )
