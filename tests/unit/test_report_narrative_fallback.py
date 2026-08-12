"""app/services/report_narrative_fallback.py — the deterministic, LLM-free
narrative (TZ_Profi.md §17.8). Must always produce output that already
passes report_narrative_validator.validate(), across sparse and rich
evidence and all three age groups, since this is what the student sees when
the LLM is unavailable or fails validation three times running.
"""
from app.models.profile import AgeGroup
from app.schemas.report_narrative_context import EvidenceItem, ReportNarrativeContext
from app.services.mi_content import MI_LABELS
from app.services.report_narrative_fallback import build_fallback_narrative
from app.services.report_narrative_validator import validate
from app.services.riasec_content import RIASEC_LABELS


def _context(age_group: AgeGroup, instrument: str, evidence: list[EvidenceItem]) -> ReportNarrativeContext:
    return ReportNarrativeContext(age_group=age_group.value, interest_instrument=instrument, evidence=evidence)


def test_fallback_is_valid_with_empty_evidence_junior():
    context = _context(AgeGroup.junior, "mi", [])
    output = build_fallback_narrative(context)
    assert validate(output, context) == []


def test_fallback_is_valid_with_empty_evidence_middle():
    context = _context(AgeGroup.middle, "riasec", [])
    output = build_fallback_narrative(context)
    assert validate(output, context) == []


def test_fallback_is_valid_with_rich_evidence_senior():
    evidence = [
        EvidenceItem(source_id="riasec:R", source_type="riasec_category", text="Реалистичный"),
        EvidenceItem(source_id="riasec:I", source_type="riasec_category", text="Исследовательский"),
        EvidenceItem(source_id="personality:openness", source_type="personality", text="Открыт новому"),
        EvidenceItem(source_id="thinking_style:creative_think", source_type="thinking_style", text="Генерация идей"),
        EvidenceItem(source_id="thinking_style:systematic", source_type="thinking_style", text="Порядок и система"),
        EvidenceItem(source_id="motivation:interest", source_type="motivation", text="Тебя драйвит интерес"),
        EvidenceItem(source_id="motivation:creation", source_type="motivation", text="Тебя драйвит создавать"),
        EvidenceItem(source_id="subject_liked:Физика", source_type="subject_liked", text="Физика"),
        EvidenceItem(source_id="artifact:1", source_type="artifact", text="Робототехника"),
    ]
    context = _context(AgeGroup.senior, "riasec", evidence)
    output = build_fallback_narrative(context)
    assert validate(output, context) == []


def test_junior_mi_interests_always_cover_all_eight_categories_regardless_of_evidence():
    context = _context(AgeGroup.junior, "mi", [])
    output = build_fallback_narrative(context)
    assert {i.category for i in output.interests} == set(MI_LABELS.keys())
    assert len(output.interests) == 8


def test_middle_senior_riasec_interests_always_cover_all_six_categories_regardless_of_evidence():
    context = _context(AgeGroup.middle, "riasec", [])
    output = build_fallback_narrative(context)
    assert {i.category for i in output.interests} == set(RIASEC_LABELS.keys())
    assert len(output.interests) == 6


def test_evidenced_interest_categories_are_tiered_strong_others_steady():
    context = _context(AgeGroup.senior, "riasec", [
        EvidenceItem(source_id="riasec:R", source_type="riasec_category", text="Реалистичный"),
    ])
    output = build_fallback_narrative(context)
    by_category = {i.category: i.tier for i in output.interests}
    assert by_category["R"] == "strong"
    assert all(tier == "steady" for cat, tier in by_category.items() if cat != "R")


def test_junior_never_gets_a_career_narrative():
    context = _context(AgeGroup.junior, "mi", [
        EvidenceItem(source_id="mi:logical", source_type="mi_category", text="Логика и счёт"),
    ])
    output = build_fallback_narrative(context)
    assert output.career_narrative == []


def test_senior_career_narrative_capped_at_three_and_grounded_in_riasec_evidence():
    evidence = [
        EvidenceItem(source_id=f"riasec:{letter}", source_type="riasec_category", text=RIASEC_LABELS[letter])
        for letter in ["R", "I", "A", "S"]
    ]
    context = _context(AgeGroup.senior, "riasec", evidence)
    output = build_fallback_narrative(context)
    assert len(output.career_narrative) == 3
    for card in output.career_narrative:
        assert set(card.evidence_ids) <= {e.source_id for e in evidence if e.source_type == "riasec_category"}


def test_strength_card_count_never_exceeds_available_evidence():
    context = _context(AgeGroup.junior, "mi", [
        EvidenceItem(source_id="mi:logical", source_type="mi_category", text="Логика и счёт"),
    ])
    output = build_fallback_narrative(context)
    assert len(output.strength_cards) == 1
