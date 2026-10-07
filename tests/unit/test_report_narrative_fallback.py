"""app/services/report_narrative_fallback.py — the deterministic, LLM-free
narrative (TZ_Profi.md §17.8). Must always produce output that already
passes report_narrative_validator.validate(), across sparse and rich
evidence and all three age groups, since this is what the student sees when
the LLM is unavailable or fails validation three times running.
"""
from app.i18n import use_locale
from app.schemas.report_narrative_context import EvidenceItem, ReportNarrativeContext
from app.services.report_narrative_fallback import build_fallback_narrative
from app.services.report_narrative_validator import validate
from app.services.riasec_content import riasec_labels
from app.services.student_strengths_service import select_strengths
from tests.strength_fixtures import rich_inputs


def _context(evidence: list[EvidenceItem], candidates=None) -> ReportNarrativeContext:
    return ReportNarrativeContext(evidence=evidence, strength_candidates=candidates or [])


def _candidates():
    with use_locale("ru"):
        return select_strengths(rich_inputs())


def test_fallback_is_valid_with_empty_evidence():
    context = _context([])
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
    ]
    context = _context(evidence, _candidates())
    output = build_fallback_narrative(context)
    assert validate(output, context) == []


def test_riasec_interests_always_cover_all_six_categories_regardless_of_evidence():
    context = _context([])
    output = build_fallback_narrative(context)
    assert {i.category for i in output.interests} == set(riasec_labels().keys())
    assert len(output.interests) == 6


def test_evidenced_interest_categories_are_tiered_strong_others_steady():
    context = _context([
        EvidenceItem(source_id="riasec:R", source_type="riasec_category", text="Реалистичный"),
    ])
    output = build_fallback_narrative(context)
    by_category = {i.category: i.tier for i in output.interests}
    assert by_category["R"] == "strong"
    assert all(tier == "steady" for cat, tier in by_category.items() if cat != "R")


def test_senior_career_narrative_capped_at_three_and_grounded_in_riasec_evidence():
    evidence = [
        EvidenceItem(source_id=f"riasec:{letter}", source_type="riasec_category", text=riasec_labels()[letter])
        for letter in ["R", "I", "A", "S"]
    ]
    context = _context(evidence)
    output = build_fallback_narrative(context)
    assert len(output.career_narrative) == 3
    for card in output.career_narrative:
        assert set(card.evidence_ids) <= {e.source_id for e in evidence if e.source_type == "riasec_category"}


def test_strength_cards_are_exactly_the_candidates_in_order():
    candidates = _candidates()
    output = build_fallback_narrative(_context([], candidates))

    assert [card.evidence_ids for card in output.strength_cards] == [[c.source_id] for c in candidates]
    assert [card.title for card in output.strength_cards] == [c.title for c in candidates]


def test_other_evidence_never_becomes_a_strength_card():
    """RIASEC / thinking style / motivation have their own sections; without
    a vetted candidate the strengths section stays empty instead of being
    padded from them (PRO-432)."""
    context = _context([
        EvidenceItem(source_id="riasec:R", source_type="riasec_category", text="Реалистичный"),
        EvidenceItem(source_id="thinking_style:creative_think", source_type="thinking_style", text="Генерация идей"),
        EvidenceItem(source_id="thinking_style:systematic", source_type="thinking_style", text="Порядок и система"),
        EvidenceItem(source_id="motivation:interest", source_type="motivation", text="Тебя драйвит интерес"),
    ])
    output = build_fallback_narrative(context)

    assert output.strength_cards == []
    # Both thinking_style signals merge into one card (not one each).
    assert len(output.thinking_style_notes) == 1
    assert set(output.thinking_style_notes[0].evidence_ids) == {
        "thinking_style:creative_think", "thinking_style:systematic",
    }
    assert output.motivation_narrative.evidence_ids == ["motivation:interest"]
    assert validate(output, context) == []


def test_thinking_style_notes_merge_two_signals_into_one_card_for_senior():
    """Two separate cards, both titled generically "Как тебе легче думать",
    read as a duplicated section (user feedback) — must merge into one card
    naming both styles, citing both source_ids."""
    context = _context([
        EvidenceItem(source_id="thinking_style:creative_think", source_type="thinking_style", text="x"),
        EvidenceItem(source_id="thinking_style:strategic", source_type="thinking_style", text="y"),
    ])
    output = build_fallback_narrative(context)

    assert len(output.thinking_style_notes) == 1
    card = output.thinking_style_notes[0]
    assert set(card.evidence_ids) == {"thinking_style:creative_think", "thinking_style:strategic"}
    assert "творческое" in card.title and "стратегическое" in card.title


def test_thinking_style_notes_single_signal_names_that_one_style_for_senior():
    context = _context([
        EvidenceItem(source_id="thinking_style:practical", source_type="thinking_style", text="x"),
    ])
    output = build_fallback_narrative(context)

    assert len(output.thinking_style_notes) == 1
    assert output.thinking_style_notes[0].title == "Тебе близко практическое мышление"


def test_thinking_style_notes_adds_personality_synthesis_for_senior_when_evidence_present():
    """User feedback: wanted thinking_style + personality combined into a
    new synthesis sentence, WITHOUT repeating the personality trait's own
    note text (that's already shown verbatim in "Твой характер" —
    report_v2_assembler.build_personality_notes)."""
    personality_text = "Ты организован, доводишь дела до конца и держишь слово"
    context = _context([
        EvidenceItem(source_id="thinking_style:systematic", source_type="thinking_style", text="x"),
        EvidenceItem(source_id="personality:conscientiousness", source_type="personality", text=personality_text),
    ])
    output = build_fallback_narrative(context)

    assert len(output.thinking_style_notes) == 1
    card = output.thinking_style_notes[0]
    assert "personality:conscientiousness" in card.evidence_ids
    assert "организованность" in card.description.lower()
    # Must NOT just repeat "Твой характер"'s own sentence verbatim.
    assert personality_text not in card.description


def test_thinking_style_notes_no_personality_synthesis_when_no_personality_evidence():
    context = _context([
        EvidenceItem(source_id="thinking_style:systematic", source_type="thinking_style", text="x"),
    ])
    output = build_fallback_narrative(context)

    card = output.thinking_style_notes[0]
    assert card.evidence_ids == ["thinking_style:systematic"]
    assert "твоя" not in card.description.lower()


def test_final_analysis_has_at_least_three_sentences_and_no_disclaimer_duplicate():
    context = _context([
        EvidenceItem(source_id="riasec:R", source_type="riasec_category", text="Любишь работать руками"),
        EvidenceItem(source_id="motivation:interest", source_type="motivation", text="Тебя драйвит интерес"),
    ])
    output = build_fallback_narrative(context)

    assert validate(output, context) == []  # includes the sentence-count + disclaimer-duplicate checks
    assert output.final_analysis


def test_final_analysis_mentions_available_sections():
    context = _context([
        EvidenceItem(source_id="riasec:R", source_type="riasec_category", text="Любишь работать руками"),
        EvidenceItem(source_id="thinking_style:systematic", source_type="thinking_style", text="x"),
        EvidenceItem(source_id="motivation:interest", source_type="motivation", text="Тебя драйвит интерес"),
    ])
    output = build_fallback_narrative(context)

    lowered = output.final_analysis.lower()
    assert "интерес" in lowered  # references the interests section
    assert "мышлени" in lowered  # references thinking style
    assert "мотивац" in lowered  # references motivation


def test_final_analysis_valid_with_no_evidence_at_all():
    """Graceful degradation — must still produce a valid 3+ sentence text
    even when there's nothing to synthesize."""
    context = _context([])
    output = build_fallback_narrative(context)

    assert validate(output, context) == []
    assert output.final_analysis


def test_motivation_narrative_joins_multiple_drivers_into_one_readable_sentence():
    """motivation_content.highlight_phrases() no longer prefixes every driver
    phrase with the same lead-in (fixed alongside this) — the fallback must
    not naively space-join the bare phrases either, or the description reads
    as several capitalized sentence fragments run together with no
    punctuation between them."""
    context = _context([
        EvidenceItem(source_id="motivation:interest", source_type="motivation",
                     text="Заниматься тем, что по-настоящему интересно"),
        EvidenceItem(source_id="motivation:creation", source_type="motivation",
                     text="Создавать что-то своё"),
    ])
    output = build_fallback_narrative(context)

    description = output.motivation_narrative.description
    assert description == "Заниматься тем, что по-настоящему интересно и создавать что-то своё."
    # No two capital letters starting a word right after "и " / ", " — that
    # would mean two fragments got glued without being turned into one flowing
    # sentence.
    assert "интересно Создавать" not in description
