"""Pure-function tests for report_v2_assembler.py — the DB-backed half of
the v2 response (interest_map/careers/is_flat_profile/exploration_activities)
that report_narrative_*'s pipeline deliberately doesn't touch. No DB, no
LLM: everything here is plain dicts/dataclasses in, ResultResponseV2 pieces
out."""

import uuid
from datetime import datetime, timezone

from app.models.profile import AgeGroup
from app.schemas.report_narrative import (
    MotivationNarrative,
    NarrativeCard,
    ReportNarrativeOutput,
)
from app.schemas.report_narrative_context import EvidenceItem, ReportNarrativeContext
from app.services import report_v2_assembler
from app.services.mi_service import MI_ORDER
from app.services.riasec_content import NEUTRAL_CAREER_WHY
from app.services.riasec_service import HOLLAND_ORDER

_NOW = datetime.now(timezone.utc)


def _context(*, age_group: str, evidence: list[EvidenceItem]) -> ReportNarrativeContext:
    return ReportNarrativeContext(
        age_group=age_group,
        interest_instrument="mi" if age_group == "junior" else "riasec",
        evidence=evidence,
    )


def _narrative(strength_cards: int = 2, thinking_style_notes: int = 1) -> ReportNarrativeOutput:
    return ReportNarrativeOutput(
        summary="Тестовое резюме.",
        strength_cards=[
            NarrativeCard(title=f"Сильная сторона {i}", description="Описание") for i in range(strength_cards)
        ],
        interests=[],
        thinking_style_notes=[
            NarrativeCard(title=f"Стиль {i}", description="Описание") for i in range(thinking_style_notes)
        ],
        motivation_narrative=MotivationNarrative(title="Драйв", description="Описание"),
        career_narrative=[],
    )


def _direction(slug: str, holland_code: str, match_score: int, first_steps: list[str] | None = None) -> dict:
    return {
        "slug": slug,
        "name": f"Направление {slug}",
        "holland_code": holland_code,
        "match_score": match_score,
        "description": "Описание направления",
        "professions": [],
        "skills_needed": ["навык"],
        "subjects_to_develop": ["предмет"],
        "first_steps": first_steps or [],
    }


def test_junior_gets_eight_mi_items_no_careers_and_activities() -> None:
    context = _context(age_group="junior", evidence=[
        EvidenceItem(source_id="mi:logical", source_type="mi_category", text="Любишь находить закономерности"),
    ])
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.junior,
        context=context,
        narrative=_narrative(),
        profile_scores={k: 40.0 for k in MI_ORDER},
        differentiation=30.0,
        careers=[_direction("swe", "RIA", 5)],  # must be ignored for junior regardless
        created_at=_NOW,
    )

    assert response.interest_instrument == "mi"
    assert len(response.interest_map) == 8
    assert {item.code for item in response.interest_map} == set(MI_ORDER)
    assert response.careers == []
    assert response.exploration_activities


def test_middle_senior_get_six_riasec_items_and_valid_career_explanations() -> None:
    context = _context(age_group="senior", evidence=[
        EvidenceItem(source_id="riasec:R", source_type="riasec_category", text="Любишь работать руками"),
    ])
    careers = [_direction("swe", "RI", 5, first_steps=["Собери первый проект"]), _direction("other", "SEC", 2)]
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={k: 40.0 for k in HOLLAND_ORDER},
        differentiation=30.0,
        careers=careers,
        created_at=_NOW,
    )

    assert response.interest_instrument == "riasec"
    assert len(response.interest_map) == 6
    assert {item.code for item in response.interest_map} == set(HOLLAND_ORDER)
    assert response.exploration_activities == []
    assert len(response.careers) == 2
    for career in response.careers:
        assert career.why  # never empty
    # The direction whose Holland code overlaps evidence gets a grounded why + try_now.
    swe = next(c for c in response.careers if c.slug == "swe")
    assert "Любишь работать руками" in swe.why
    assert swe.try_now == "Собери первый проект"
    # The one with no overlapping evidence still gets the neutral fallback, never blank.
    other = next(c for c in response.careers if c.slug == "other")
    assert other.why == NEUTRAL_CAREER_WHY


def test_flat_profile_gives_exactly_three_worth_trying_careers() -> None:
    context = _context(age_group="senior", evidence=[])
    careers = [_direction(f"d{i}", "RIA", 5 - i) for i in range(5)]
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={k: 50.0 for k in HOLLAND_ORDER},  # flat: no spread at all
        differentiation=5.0,  # below the flat threshold
        careers=careers,
        created_at=_NOW,
    )

    assert response.is_flat_profile is True
    assert len(response.careers) == 3
    assert all(c.tier == "worth_trying" for c in response.careers)


def test_flat_profile_with_artifact_evidence_gets_an_honest_summary_note() -> None:
    """career_match_score only ever looks at the RIASEC top-3 code — on a
    flat profile that top-3 is close to noise, and it never sees
    subject/artifact evidence at all. Found live: a student with clear
    self-reported programming/robotics interest got three clerical
    directions with zero connection to it. The scoped mitigation is telling
    the reader honestly, not silently presenting a noisy top-3 as fact."""
    context = _context(age_group="senior", evidence=[
        EvidenceItem(source_id="artifact:1", source_type="artifact", text="Программирование"),
    ])
    careers = [_direction(f"d{i}", "RIA", 5 - i) for i in range(5)]
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={k: 50.0 for k in HOLLAND_ORDER},
        differentiation=5.0,
        careers=careers,
        created_at=_NOW,
    )

    assert response.is_flat_profile is True
    assert "увлечения" in response.summary


def test_flat_profile_without_artifact_evidence_gets_no_note() -> None:
    context = _context(age_group="senior", evidence=[])
    careers = [_direction(f"d{i}", "RIA", 5 - i) for i in range(5)]
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={k: 50.0 for k in HOLLAND_ORDER},
        differentiation=5.0,
        careers=careers,
        created_at=_NOW,
    )

    assert response.summary == _narrative().summary


def test_non_flat_profile_with_artifact_evidence_gets_no_note() -> None:
    context = _context(age_group="senior", evidence=[
        EvidenceItem(source_id="artifact:1", source_type="artifact", text="Программирование"),
    ])
    careers = [_direction(f"d{i}", "RIA", 5 - i) for i in range(5)]
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={"R": 90.0, "I": 10.0, "A": 10.0, "S": 10.0, "E": 10.0, "C": 10.0},
        differentiation=80.0,
        careers=careers,
        created_at=_NOW,
    )

    assert response.is_flat_profile is False
    assert response.summary == _narrative().summary


def test_junior_never_gets_the_flat_profile_artifact_note() -> None:
    """MiResultResponse has no careers at all — the note references
    "направления... в списке ниже", which doesn't exist for junior."""
    context = _context(age_group="junior", evidence=[
        EvidenceItem(source_id="artifact:1", source_type="artifact", text="Программирование"),
    ])
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.junior,
        context=context,
        narrative=_narrative(),
        profile_scores={k: 50.0 for k in MI_ORDER},
        differentiation=5.0,
        careers=[],
        created_at=_NOW,
    )

    assert response.is_flat_profile is True
    assert response.summary == _narrative().summary


def test_non_flat_profile_tiers_are_strong_good_worth_trying_by_rank() -> None:
    context = _context(age_group="senior", evidence=[])
    careers = [_direction(f"d{i}", "RIA", 5 - i) for i in range(5)]
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={"R": 90.0, "I": 10.0, "A": 10.0, "S": 10.0, "E": 10.0, "C": 10.0},
        differentiation=80.0,  # well above the flat threshold
        careers=careers,
        created_at=_NOW,
    )

    assert response.is_flat_profile is False
    tiers = [c.tier for c in response.careers]
    assert tiers == ["strong", "good", "good", "worth_trying", "worth_trying"]


def test_same_context_gives_identical_fallback_output() -> None:
    """Determinism: no randomness, no unordered-dict dependence anywhere —
    calling twice with the same inputs must produce byte-identical output."""
    context = _context(age_group="senior", evidence=[
        EvidenceItem(source_id="riasec:R", source_type="riasec_category", text="Любишь работать руками"),
        EvidenceItem(source_id="riasec:I", source_type="riasec_category", text="Любишь докапываться до сути"),
    ])
    careers = [_direction("swe", "RI", 5), _direction("bio", "IS", 3)]
    profile_scores = {"R": 80.0, "I": 75.0, "A": 20.0, "S": 30.0, "E": 40.0, "C": 10.0}
    narrative = _narrative()
    assessment_id = uuid.uuid4()

    kwargs = dict(
        assessment_id=assessment_id, age_group=AgeGroup.senior, context=context, narrative=narrative,
        profile_scores=profile_scores, differentiation=45.0, careers=careers, created_at=_NOW,
    )
    first = report_v2_assembler.assemble_result_v2(**kwargs)
    second = report_v2_assembler.assemble_result_v2(**kwargs)

    assert first.model_dump() == second.model_dump()


def test_interest_map_levels_follow_documented_thresholds() -> None:
    context = _context(age_group="senior", evidence=[])
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={"R": 75.0, "I": 55.0, "A": 20.0, "S": 0.0, "E": 50.0, "C": 100.0},
        differentiation=100.0,
        careers=[],
        created_at=_NOW,
    )

    levels = {item.code: item.level for item in response.interest_map}
    assert levels["R"] == "high"    # >= 70
    assert levels["I"] == "medium"  # >= 50, < 70
    assert levels["A"] == "low"     # < 50
    assert levels["S"] == "low"
    assert levels["E"] == "medium"  # exactly 50
    assert levels["C"] == "high"
