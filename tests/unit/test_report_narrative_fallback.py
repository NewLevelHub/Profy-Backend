"""app/services/report_narrative_fallback.py — the deterministic, LLM-free
narrative (TZ_Profi.md §17.8). Must always produce output that already
passes report_narrative_validator.validate(), across sparse and rich
evidence and all three age groups, since this is what the student sees when
the LLM is unavailable or fails validation three times running.
"""
from app.models.profile import AgeGroup
from app.schemas.report_narrative_context import EvidenceItem, ReportNarrativeContext
from app.services.mi_content import mi_labels
from app.services.report_narrative_fallback import build_fallback_narrative
from app.services.report_narrative_validator import validate
from app.services.riasec_content import riasec_labels


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
    assert {i.category for i in output.interests} == set(mi_labels().keys())
    assert len(output.interests) == 8


def test_middle_senior_riasec_interests_always_cover_all_six_categories_regardless_of_evidence():
    context = _context(AgeGroup.middle, "riasec", [])
    output = build_fallback_narrative(context)
    assert {i.category for i in output.interests} == set(riasec_labels().keys())
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
        EvidenceItem(source_id=f"riasec:{letter}", source_type="riasec_category", text=riasec_labels()[letter])
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


def test_thinking_style_and_motivation_evidence_never_leak_into_strength_cards_even_when_sparse():
    """With only 1 non-excluded fact available, a naive "first N of the
    whole evidence list" implementation would pad strength_cards out with
    thinking_style/motivation items too — duplicating them verbatim against
    thinking_style_notes / the "Что тебя драйвит" motivation section
    (TZ_Profi.md §18.2 п.2 vs п.4/п.5 are three separate sections). Confirms
    that doesn't happen even in this sparse case."""
    context = _context(AgeGroup.senior, "riasec", [
        EvidenceItem(source_id="riasec:R", source_type="riasec_category", text="Реалистичный"),
        EvidenceItem(source_id="thinking_style:creative_think", source_type="thinking_style", text="Генерация идей"),
        EvidenceItem(source_id="thinking_style:systematic", source_type="thinking_style", text="Порядок и система"),
        EvidenceItem(source_id="motivation:interest", source_type="motivation", text="Тебя драйвит интерес"),
    ])
    output = build_fallback_narrative(context)

    assert len(output.strength_cards) == 1
    assert output.strength_cards[0].evidence_ids == ["riasec:R"]
    # Both thinking_style signals merge into one card (not one each) —
    # see test_thinking_style_notes_merge_two_signals_into_one_card below.
    assert len(output.thinking_style_notes) == 1
    assert set(output.thinking_style_notes[0].evidence_ids) == {
        "thinking_style:creative_think", "thinking_style:systematic",
    }
    assert output.motivation_narrative.evidence_ids == ["motivation:interest"]
    strength_card_evidence_ids = {sid for card in output.strength_cards for sid in card.evidence_ids}
    assert not strength_card_evidence_ids & {
        "thinking_style:creative_think", "thinking_style:systematic", "motivation:interest",
    }


def test_thinking_style_notes_merge_two_signals_into_one_card_for_senior():
    """Two separate cards, both titled generically "Как тебе легче думать",
    read as a duplicated section (user feedback) — must merge into one card
    naming both styles, citing both source_ids."""
    context = _context(AgeGroup.senior, "riasec", [
        EvidenceItem(source_id="thinking_style:creative_think", source_type="thinking_style", text="x"),
        EvidenceItem(source_id="thinking_style:strategic", source_type="thinking_style", text="y"),
    ])
    output = build_fallback_narrative(context)

    assert len(output.thinking_style_notes) == 1
    card = output.thinking_style_notes[0]
    assert set(card.evidence_ids) == {"thinking_style:creative_think", "thinking_style:strategic"}
    assert "творческое" in card.title and "стратегическое" in card.title


def test_thinking_style_notes_single_signal_names_that_one_style_for_senior():
    context = _context(AgeGroup.senior, "riasec", [
        EvidenceItem(source_id="thinking_style:practical", source_type="thinking_style", text="x"),
    ])
    output = build_fallback_narrative(context)

    assert len(output.thinking_style_notes) == 1
    assert output.thinking_style_notes[0].title == "Тебе близко практическое мышление"


def test_thinking_style_notes_junior_has_no_style_labels_or_career_language():
    """TZ_Profi.md §4.1: junior gets no abstract typology labels and no
    career/work-adjacent framing anywhere — thinking_style_notes must stay
    purely behavioral even when merging two signals into one card."""
    context = _context(AgeGroup.junior, "mi", [
        EvidenceItem(source_id="thinking_style:creative_think", source_type="thinking_style", text="x"),
        EvidenceItem(source_id="thinking_style:systematic", source_type="thinking_style", text="y"),
    ])
    output = build_fallback_narrative(context)

    assert len(output.thinking_style_notes) == 1
    card = output.thinking_style_notes[0]
    assert card.title == "Как тебе легче думать"
    for banned in ("творческое", "системное", "мышление", "работ", "роль", "карьер"):
        assert banned not in card.description.lower()
    assert validate(output, context) == []


def test_thinking_style_notes_adds_personality_synthesis_for_senior_when_evidence_present():
    """User feedback: wanted thinking_style + personality combined into a
    new synthesis sentence, WITHOUT repeating the personality trait's own
    note text (that's already shown verbatim in "Твой характер" —
    report_v2_assembler.build_personality_notes)."""
    personality_text = "Ты организован, доводишь дела до конца и держишь слово"
    context = _context(AgeGroup.senior, "riasec", [
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
    context = _context(AgeGroup.senior, "riasec", [
        EvidenceItem(source_id="thinking_style:systematic", source_type="thinking_style", text="x"),
    ])
    output = build_fallback_narrative(context)

    card = output.thinking_style_notes[0]
    assert card.evidence_ids == ["thinking_style:systematic"]
    assert "твоя" not in card.description.lower()


def test_thinking_style_notes_junior_never_gets_personality_synthesis():
    """TZ_Profi.md §4.1: junior gets no trait labels at all, even when
    personality evidence exists in the catalog."""
    context = _context(AgeGroup.junior, "mi", [
        EvidenceItem(source_id="thinking_style:systematic", source_type="thinking_style", text="x"),
        EvidenceItem(source_id="personality:conscientiousness", source_type="personality", text="Ты организован"),
    ])
    output = build_fallback_narrative(context)

    card = output.thinking_style_notes[0]
    assert "personality:conscientiousness" not in card.evidence_ids
    assert "организован" not in card.description.lower()


def test_final_analysis_has_at_least_three_sentences_and_no_disclaimer_duplicate():
    context = _context(AgeGroup.senior, "riasec", [
        EvidenceItem(source_id="riasec:R", source_type="riasec_category", text="Любишь работать руками"),
        EvidenceItem(source_id="motivation:interest", source_type="motivation", text="Тебя драйвит интерес"),
    ])
    output = build_fallback_narrative(context)

    assert validate(output, context) == []  # includes the sentence-count + disclaimer-duplicate checks
    assert output.final_analysis


def test_final_analysis_mentions_available_sections():
    context = _context(AgeGroup.senior, "riasec", [
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
    context = _context(AgeGroup.junior, "mi", [])
    output = build_fallback_narrative(context)

    assert validate(output, context) == []
    assert output.final_analysis


def test_strength_card_title_is_the_specific_observation_not_a_generic_bucket_label():
    """TZ_Profi.md §18.2 п.2 wants each card's own short formulation as the
    headline (e.g. "Ты замечаешь, когда что-то не работает и хочешь
    разобраться почему"), not a repeated category label like "Тебе
    интересно" — otherwise every interest-derived card looks identically
    titled. The evidence text (already a specific, human formulation) is
    the title; the description grounds it in how it was observed."""
    context = _context(AgeGroup.senior, "riasec", [
        EvidenceItem(source_id="riasec:R", source_type="riasec_category", text="Любишь работать руками"),
    ])
    output = build_fallback_narrative(context)

    card = output.strength_cards[0]
    assert card.title == "Любишь работать руками"
    assert card.description != card.title
    assert card.description


def test_motivation_narrative_joins_multiple_drivers_into_one_readable_sentence():
    """motivation_content.highlight_phrases() no longer prefixes every driver
    phrase with the same lead-in (fixed alongside this) — the fallback must
    not naively space-join the bare phrases either, or the description reads
    as several capitalized sentence fragments run together with no
    punctuation between them."""
    context = _context(AgeGroup.senior, "riasec", [
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


def test_onboarding_sourced_strength_cards_are_explicitly_marked_as_not_from_the_test():
    """subject_liked/subject_easy/artifact are self-reported at onboarding,
    not measured by the test — the card must say so plainly, so a reader
    doesn't mistake it for part of what the test (and therefore the shown
    careers) actually found. User feedback: seeing a "programming" card
    next to an "accountant" suggestion read as if the app didn't know what
    it was talking about."""
    for source_type in ("subject_liked", "subject_easy", "artifact"):
        context = _context(AgeGroup.senior, "riasec", [
            EvidenceItem(source_id=f"{source_type}:x", source_type=source_type, text="Программирование"),
        ])
        output = build_fallback_narrative(context)
        assert len(output.strength_cards) == 1
        assert "не из теста" in output.strength_cards[0].description.lower()
