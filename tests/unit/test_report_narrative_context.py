"""build_report_narrative_context is a pure function — no DB session needed.
Covers the acceptance bar: every item has source_id/source_type/text;
interests come as RIASEC evidence; unknown source_ids are rejected; and —
the actual point of
the whole catalog — nothing here ever carries a raw score or a percentage."""

import re

from app.schemas.student_strengths import StrengthCandidate
from app.services.report_narrative_context import (
    build_report_narrative_context,
    unknown_source_ids,
)

_HAS_DIGIT = re.compile(r"\d")


def test_every_evidence_item_has_source_id_type_and_text() -> None:
    context = build_report_narrative_context(
        strengths=["R", "I"],
        personality_profile={"openness": 70.0, "conscientiousness": 30.0},
        personality_notes={"openness": "Тебе интересно узнавать новое", "conscientiousness": "..."},
        thinking_style={"creative_think": 80.0, "systematic": 20.0, "strategic": 60.0, "practical": 10.0},
        motivation_top=["interest", "creation"],
        motivation_highlights=[
            "Тебя больше всего драйвит — заниматься тем, что по-настоящему интересно",
            "Тебя больше всего драйвит — создавать что-то своё",
        ],
    )

    assert context.evidence, "should not be empty for this input"
    for item in context.evidence:
        assert item.source_id
        assert item.source_type
        assert item.text


def test_context_has_riasec_evidence() -> None:
    context = build_report_narrative_context(
        strengths=["R", "I"],
        personality_profile={},
        personality_notes={},
        thinking_style={},
        motivation_top=[],
        motivation_highlights=[],
    )

    riasec_items = [e for e in context.evidence if e.source_type == "riasec_category"]
    assert {e.source_id for e in riasec_items} == {"riasec:R", "riasec:I"}


def test_personality_evidence_only_includes_high_tier_traits() -> None:
    context = build_report_narrative_context(
        strengths=[],
        personality_profile={"openness": 75.0, "conscientiousness": 45.0, "agreeableness": 20.0},
        personality_notes={
            "openness": "высокая открытость",
            "conscientiousness": "средняя добросовестность",
            "agreeableness": "низкая доброжелательность",
        },
        thinking_style={},
        motivation_top=[], motivation_highlights=[],
    )

    personality_items = [e for e in context.evidence if e.source_type == "personality"]
    assert {e.source_id for e in personality_items} == {"personality:openness"}


def test_thinking_style_evidence_picks_top_two_deterministically_on_ties() -> None:
    context = build_report_narrative_context(
        strengths=[],
        personality_profile={}, personality_notes={},
        # creative_think and systematic tie at 50 — fixed order must break the tie.
        thinking_style={"creative_think": 50.0, "systematic": 50.0, "strategic": 10.0, "practical": 10.0},
        motivation_top=[], motivation_highlights=[],
    )

    thinking_items = [e for e in context.evidence if e.source_type == "thinking_style"]
    assert [e.source_id for e in thinking_items] == ["thinking_style:creative_think", "thinking_style:systematic"]


def test_thinking_style_evidence_omitted_when_there_is_no_real_signal() -> None:
    """No data (empty dict) or a genuine 0.0 for every category must not
    still hand out a confident-looking "top 2" — that would be a fact this
    catalog fabricated, not one it observed."""
    empty = build_report_narrative_context(
        strengths=[],
        personality_profile={}, personality_notes={},
        thinking_style={},
        motivation_top=[], motivation_highlights=[],
    )
    all_zero = build_report_narrative_context(
        strengths=[],
        personality_profile={}, personality_notes={},
        thinking_style={"creative_think": 0.0, "systematic": 0.0, "strategic": 0.0, "practical": 0.0},
        motivation_top=[], motivation_highlights=[],
    )

    assert not any(e.source_type == "thinking_style" for e in empty.evidence)
    assert not any(e.source_type == "thinking_style" for e in all_zero.evidence)


def test_thinking_style_evidence_includes_only_the_one_real_signal() -> None:
    """A partial signal (one non-zero category) must yield exactly that one
    item, not padded out to 2 with unmeasured categories."""
    context = build_report_narrative_context(
        strengths=[],
        personality_profile={}, personality_notes={},
        thinking_style={"creative_think": 40.0, "systematic": 0.0, "strategic": 0.0, "practical": 0.0},
        motivation_top=[], motivation_highlights=[],
    )

    thinking_items = [e for e in context.evidence if e.source_type == "thinking_style"]
    assert [e.source_id for e in thinking_items] == ["thinking_style:creative_think"]


def test_unknown_source_ids_are_rejected() -> None:
    context = build_report_narrative_context(
        strengths=["R"],
        personality_profile={}, personality_notes={}, thinking_style={},
        motivation_top=[], motivation_highlights=[],
    )

    rejected = unknown_source_ids(context, ["riasec:R", "riasec:Z", "made_up:thing"])

    assert rejected == {"riasec:Z", "made_up:thing"}


def test_evidence_contains_no_raw_numbers_or_percent_signs() -> None:
    """The actual point of the catalog: none of the *derived/categorical*
    evidence (interests, personality, motivation, thinking style — the
    labels this module itself writes) is a score."""
    context = build_report_narrative_context(
        strengths=["R", "I", "A"],
        personality_profile={
            "openness": 90.0, "conscientiousness": 85.0,
            "extraversion": 40.0, "agreeableness": 40.0, "emotional_stability": 40.0,
        },
        personality_notes={"openness": "Тебе интересно узнавать новое", "conscientiousness": "Ты организован"},
        thinking_style={"creative_think": 90.0, "systematic": 85.0, "strategic": 10.0, "practical": 5.0},
        motivation_top=["interest"],
        motivation_highlights=["Тебя больше всего драйвит — заниматься тем, что по-настоящему интересно"],
    )

    derived_types = {"riasec_category", "personality", "motivation", "thinking_style"}
    derived_items = [e for e in context.evidence if e.source_type in derived_types]
    assert derived_items, "sanity check: this input should produce derived evidence"
    for item in derived_items:
        assert "%" not in item.text
        assert not _HAS_DIGIT.search(item.text), f"evidence text looks numeric: {item.text!r}"


def _candidate(source_id: str) -> StrengthCandidate:
    return StrengthCandidate(
        source_id=source_id, source_type="elers", domain="self_regulation", basis="self_report",
        content_key="elers", evidence_ids=["elers"], priority=5, title="t", description="d",
    )


def test_strength_candidates_are_carried_and_citable() -> None:
    """PRO-432: strength cards cite the vetted candidates, which therefore
    count as known ids next to the evidence catalog."""
    context = build_report_narrative_context(
        strengths=["R"],
        personality_profile={}, personality_notes={}, thinking_style={},
        motivation_top=[], motivation_highlights=[],
        strength_candidates=[_candidate("strength:elers")],
    )

    assert [c.source_id for c in context.strength_candidates] == ["strength:elers"]
    assert unknown_source_ids(context, ["strength:elers", "riasec:R", "strength:made_up"]) == {"strength:made_up"}
    # Onboarding facts no longer enter the evidence catalog at all — they
    # reach the report only as a strength candidate.
    assert {e.source_type for e in context.evidence} == {"riasec_category"}
