"""PRO-338 Ф0.2 — isolation guarantee for the 6 new-tests specialist
sections: a malformed container for one test must not blank the others,
same contract as report_service's existing section builders."""
import uuid

from app.models.analysis_result import AnalysisResult
from app.services.new_tests_report_service import build_new_tests_sections


def _bare_analysis_result(**overrides) -> AnalysisResult:
    return AnalysisResult(id=uuid.uuid4(), assessment_id=uuid.uuid4(), **overrides)


def test_no_data_yields_all_none_sections():
    result = build_new_tests_sections(_bare_analysis_result())

    assert result.professional_types is None
    assert result.team_role is None
    assert result.temperament is None
    assert result.intelligence is None
    assert result.aspiration_level is None
    assert result.empathy_confidence is None


def test_populated_containers_build_their_sections():
    analysis_result = _bare_analysis_result(
        professional_types={"interest_scores": {"practical": 5}, "hybrid_profile": ["practical", "technical"]},
        eysenck={"extraversion_raw": 12, "neuroticism_raw": 8, "protocol_flagged": False},
        elers={"score": 20, "level": "moderate"},
        empathy_confidence={"empathy_total": 20.0, "confidence_stens": 6},
    )

    result = build_new_tests_sections(analysis_result)

    assert result.professional_types.hybrid_profile == ["practical", "technical"]
    assert result.temperament.extraversion_raw == 12
    assert result.aspiration_level.level == "moderate"
    assert result.empathy_confidence.confidence_stens == 6
    # Belbin/АСТУР have no container yet (own tables land in Ф2.3/Ф3.3)
    assert result.team_role is None
    assert result.intelligence is None


def test_one_malformed_container_does_not_blank_the_others():
    """extra='forbid' rejects an unknown key — the eysenck container here
    has a typo'd field, which must only null out `temperament`, not the
    sibling sections built from clean containers."""
    analysis_result = _bare_analysis_result(
        professional_types={"interest_scores": {"artistic": 7}},
        eysenck={"not_a_real_field": 1},
        elers={"score": 15},
    )

    result = build_new_tests_sections(analysis_result)

    assert result.professional_types.interest_scores == {"artistic": 7}
    assert result.aspiration_level.score == 15
    assert result.temperament is None
