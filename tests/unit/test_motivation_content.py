"""app/services/motivation_content.py — highlight_phrases() builds the
student-facing motivation_highlights list (report_v2_assembler.py reads its
output straight from ReportNarrativeContext.evidence, one item per phrase)."""
from app.services.motivation_content import highlight_phrases


def test_highlight_phrases_have_no_shared_repeated_lead_in():
    """Previously every phrase was prefixed with "Тебя больше всего драйвит
    — ", so 2-3 top motivators read as the same sentence stuttering 2-3
    times (this is the exact bug the user reported live)."""
    phrases = highlight_phrases(["interest", "creation", "teamwork"])

    assert len(phrases) == 3
    assert len(set(phrases)) == 3, "each phrase must be distinct, not a shared prefix + different tail"
    for phrase in phrases:
        assert "драйвит" not in phrase.lower()


def test_highlight_phrases_are_capitalized_standalone_sentences():
    """Each phrase is now shown on its own (frontend MotivationSection.tsx
    renders one Card per item) — it must read as a complete, capitalized
    sentence fragment on its own, not a continuation of an implied lead-in."""
    phrases = highlight_phrases(["interest"])

    assert phrases == ["Заниматься тем, что по-настоящему интересно"]
    assert phrases[0][0].isupper()


def test_highlight_phrases_skips_unknown_categories():
    assert highlight_phrases(["not_a_real_category"]) == []
