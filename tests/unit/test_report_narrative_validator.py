"""app/services/report_narrative_validator.py — the gate a structurally
valid LLM JSON response still has to pass before it's trusted. Every test
starts from a known-good baseline (report_narrative_fallback's own output,
which is guaranteed valid — see test_report_narrative_fallback.py) and
mutates exactly one thing, so a failure always isolates to one rule.
"""
from app.models.profile import AgeGroup
from app.schemas.report_narrative import NarrativeCard
from app.schemas.report_narrative_context import EvidenceItem, ReportNarrativeContext
from app.services.report_narrative_fallback import build_fallback_narrative
from app.services.report_narrative_validator import validate


def _context(age_group: AgeGroup, instrument: str, evidence: list[EvidenceItem]) -> ReportNarrativeContext:
    return ReportNarrativeContext(age_group=age_group.value, interest_instrument=instrument, evidence=evidence)


def _junior_context() -> ReportNarrativeContext:
    return _context(AgeGroup.junior, "mi", [
        EvidenceItem(source_id="mi:logical", source_type="mi_category", text="Логика и счёт"),
        EvidenceItem(source_id="mi:musical", source_type="mi_category", text="Музыка и ритм"),
        EvidenceItem(source_id="motivation:interest", source_type="motivation", text="Тебя драйвит интерес"),
    ])


def _senior_context() -> ReportNarrativeContext:
    return _context(AgeGroup.senior, "riasec", [
        EvidenceItem(source_id="riasec:R", source_type="riasec_category", text="Реалистичный"),
        EvidenceItem(source_id="riasec:I", source_type="riasec_category", text="Исследовательский"),
        EvidenceItem(source_id="personality:openness", source_type="personality", text="Открыт новому"),
        EvidenceItem(source_id="personality:conscientiousness", source_type="personality", text="Доводит дело до конца"),
        EvidenceItem(source_id="thinking_style:creative_think", source_type="thinking_style", text="Генерация идей"),
        EvidenceItem(source_id="motivation:interest", source_type="motivation", text="Тебя драйвит интерес"),
    ])


def test_valid_fallback_output_has_no_issues_junior():
    context = _junior_context()
    assert validate(build_fallback_narrative(context), context) == []


def test_valid_fallback_output_has_no_issues_senior():
    context = _senior_context()
    assert validate(build_fallback_narrative(context), context) == []


def test_structurally_valid_but_banned_phrase_is_rejected():
    context = _senior_context()
    output = build_fallback_narrative(context)
    output.strength_cards[0].description = "У тебя низкий результат, но это нормально"

    issues = validate(output, context)

    assert any(i.code == "banned_phrase" for i in issues)


def test_junior_career_narrative_is_rejected():
    context = _junior_context()
    output = build_fallback_narrative(context)
    output.career_narrative = [
        NarrativeCard(title="Профессии", description="Можно стать инженером", evidence_ids=["mi:logical"])
    ]

    issues = validate(output, context)

    assert any(i.code == "junior_career_narrative" for i in issues)


def test_junior_career_term_in_any_section_is_rejected():
    context = _junior_context()
    output = build_fallback_narrative(context)
    output.summary = "Тебе подойдёт профессия инженера"

    issues = validate(output, context)

    assert any(i.code == "junior_career_term" for i in issues)


def test_mi_interest_count_must_be_exactly_eight():
    context = _junior_context()
    output = build_fallback_narrative(context)
    output.interests = output.interests[:-1]

    issues = validate(output, context)

    assert any(i.code == "interest_count" for i in issues)


def test_riasec_interest_count_must_be_exactly_six():
    context = _senior_context()
    output = build_fallback_narrative(context)
    output.interests = output.interests[:-1]

    issues = validate(output, context)

    assert any(i.code == "interest_count" for i in issues)


def test_interest_category_set_must_match_the_instrument():
    context = _senior_context()
    output = build_fallback_narrative(context)
    output.interests[0].category = "not_a_real_category"

    issues = validate(output, context)

    assert any(i.code == "interest_cardinality" for i in issues)


def test_interest_marked_strong_without_matching_evidence_is_rejected():
    context = _senior_context()
    output = build_fallback_narrative(context)
    steady_item = next(i for i in output.interests if i.tier == "steady")
    steady_item.tier = "strong"

    issues = validate(output, context)

    assert any(i.code == "interest_tier_unsupported" and i.detail == steady_item.category for i in issues)


def test_unknown_evidence_id_is_rejected():
    context = _senior_context()
    output = build_fallback_narrative(context)
    output.strength_cards[0].evidence_ids = ["made_up:thing"]

    issues = validate(output, context)

    assert any(i.code == "unknown_evidence_id" and i.detail == "made_up:thing" for i in issues)


def test_thinking_style_count_must_match_real_signal_count():
    context = _junior_context()  # no thinking_style evidence at all
    output = build_fallback_narrative(context)
    assert output.thinking_style_notes == []
    output.thinking_style_notes = [
        NarrativeCard(title="Как тебе легче думать", description="Ты мыслишь стратегически", evidence_ids=[])
    ]

    issues = validate(output, context)

    assert any(i.code == "thinking_style_count" for i in issues)


def test_strength_card_count_below_minimum_is_rejected():
    context = _senior_context()  # 6 evidence items -> expects min(5,6)=5
    output = build_fallback_narrative(context)
    output.strength_cards = output.strength_cards[:2]

    issues = validate(output, context)

    assert any(i.code == "strength_card_count" for i in issues)


def test_strength_card_count_matches_sparse_evidence_exactly():
    """With only 2 evidence items available, exactly 2 cards is correct —
    the validator must not demand 5 cards out of thin air."""
    context = _junior_context()  # 3 evidence items total
    output = build_fallback_narrative(context)

    issues = validate(output, context)

    assert len(output.strength_cards) == 3
    assert not any(i.code == "strength_card_count" for i in issues)


def test_career_narrative_cannot_exceed_three_cards_for_senior():
    context = _senior_context()
    output = build_fallback_narrative(context)
    output.career_narrative = [
        NarrativeCard(title=f"Направление {i}", description="Стоит попробовать", evidence_ids=["riasec:R"])
        for i in range(4)
    ]

    issues = validate(output, context)

    assert any(i.code == "career_narrative_count" for i in issues)


def test_career_narrative_must_cite_riasec_evidence():
    context = _senior_context()
    output = build_fallback_narrative(context)
    output.career_narrative = [
        NarrativeCard(title="Направление", description="Стоит попробовать", evidence_ids=[])
    ]

    issues = validate(output, context)

    assert any(i.code == "career_narrative_evidence" for i in issues)


def test_motivation_ungrounded_when_evidence_exists_but_not_cited():
    context = _senior_context()  # has motivation:interest evidence
    output = build_fallback_narrative(context)
    output.motivation_narrative.evidence_ids = []

    issues = validate(output, context)

    assert any(i.code == "motivation_ungrounded" for i in issues)


def test_numeric_leak_is_rejected():
    context = _senior_context()
    output = build_fallback_narrative(context)
    output.summary = output.summary + " Совпадение 87%."

    issues = validate(output, context)

    assert any(i.code == "numeric_leak" for i in issues)


def test_non_russian_text_is_rejected_for_ru_language():
    context = _senior_context()
    output = build_fallback_narrative(context)
    output.summary = "This report is entirely in English for testing purposes only right now."

    issues = validate(output, context, language="ru")

    assert any(i.code == "language" for i in issues)


def test_summary_too_long_for_junior_is_rejected():
    context = _junior_context()
    output = build_fallback_narrative(context)
    output.summary = "Тебе интересно очень многое. " * 30

    issues = validate(output, context)

    assert any(i.code == "summary_length" for i in issues)


def test_card_description_too_long_is_rejected():
    context = _senior_context()
    output = build_fallback_narrative(context)
    output.strength_cards[0].description = "Ты умеешь очень многое и это правда здорово, поверь мне. " * 10

    issues = validate(output, context)

    assert any(i.code == "card_length" for i in issues)
