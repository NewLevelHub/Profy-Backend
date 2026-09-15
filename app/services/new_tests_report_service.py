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

logger = logging.getLogger(__name__)


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


def _build_team_role_section(analysis_result: AnalysisResult) -> TeamRoleSection | None:
    """Belbin has no data source yet — its own ipsative-battery table
    (belbin_runs) lands in Ф2.3 (03-Фаза2-Белбин.md). Kept as its own
    isolated builder now so wiring it into the specialist report later only
    touches this function's body, not the aggregator or the response
    schema."""
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


def build_new_tests_sections(analysis_result: AnalysisResult) -> NewTestsSections:
    """Always succeeds, never raises — every field independently falls back
    to None on its own builder's failure (see module docstring)."""
    return NewTestsSections(
        professional_types=_build_professional_types_section(analysis_result),
        team_role=_build_team_role_section(analysis_result),
        temperament=_build_temperament_section(analysis_result),
        intelligence=_build_intelligence_section(analysis_result),
        aspiration_level=_build_aspiration_level_section(analysis_result),
        empathy_confidence=_build_empathy_confidence_section(analysis_result),
    )
