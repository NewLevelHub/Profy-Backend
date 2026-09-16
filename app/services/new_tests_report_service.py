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
from app.services import belbin_service

logger = logging.getLogger(__name__)

# Ф2.7 / epic decision table §2: Belbin's source is 18+/corporate-context —
# a methodical note for the specialist, never a code-gated restriction (the
# platform's own age range, 14-18, is otherwise unaffected — see
# 00-ЭПИК-PRO-338.md's "Возраст" row).
_BELBIN_METHODOLOGICAL_NOTE = (
    "Методика Белбина изначально разработана для взрослых сотрудников в "
    "корпоративном контексте (18+). Результат школьника стоит трактовать с "
    "поправкой на возраст — это не формальное ограничение платформы, а "
    "методическая особенность источника."
)


def _build_professional_types_section(analysis_result: AnalysisResult) -> ProfessionalTypesSection | None:
    """ДДО — scored in Ф1 (02-Фаза1-Лёгкие-тесты.md); `None` until that
    service writes AnalysisResult.professional_types."""
    try:
        data = analysis_result.professional_types
        if not data:
            return None
        return ProfessionalTypesSection(**data)
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
        )
    except Exception:
        logger.exception("Failed to build team_role section for assessment %s", assessment_id)
        return None


def _build_temperament_section(analysis_result: AnalysisResult) -> TemperamentSection | None:
    """Eysenck — scored in Ф1; `None` until that service writes
    AnalysisResult.eysenck."""
    try:
        data = analysis_result.eysenck
        if not data:
            return None
        return TemperamentSection(**data)
    except Exception:
        logger.exception("Failed to build temperament section for analysis_result %s", analysis_result.id)
        return None


def _build_intelligence_section(analysis_result: AnalysisResult) -> IntelligenceSection | None:
    """АСТУР has no data source yet — its own timed-subtest table lands in
    Ф3.3 (04-Фаза3-АСТУР.md). Isolated builder for the same reason as
    _build_team_role_section above."""
    return None


def _build_aspiration_level_section(analysis_result: AnalysisResult) -> AspirationLevelSection | None:
    """Elers — scored in Ф1; `None` until that service writes
    AnalysisResult.elers."""
    try:
        data = analysis_result.elers
        if not data:
            return None
        return AspirationLevelSection(**data)
    except Exception:
        logger.exception("Failed to build aspiration_level section for analysis_result %s", analysis_result.id)
        return None


def _build_empathy_confidence_section(analysis_result: AnalysisResult) -> EmpathyConfidenceSection | None:
    """Бойко + Кондаш/Прихожан — scored in Ф1; `None` until that service
    writes AnalysisResult.empathy_confidence."""
    try:
        data = analysis_result.empathy_confidence
        if not data:
            return None
        return EmpathyConfidenceSection(**data)
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
        professional_types=_build_professional_types_section(analysis_result),
        team_role=await _build_team_role_section(assessment_id, db),
        temperament=_build_temperament_section(analysis_result),
        intelligence=_build_intelligence_section(analysis_result),
        aspiration_level=_build_aspiration_level_section(analysis_result),
        empathy_confidence=_build_empathy_confidence_section(analysis_result),
    )
