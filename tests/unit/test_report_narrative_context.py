"""build_report_narrative_context is a pure function — no DB session needed.
Covers the acceptance bar: every item has source_id/source_type/text; junior
gets MI evidence and never RIASEC; middle/senior gets RIASEC evidence;
Harter-pair and MOST/LEAST-triplet motivation inputs produce the same
evidence shape; unknown source_ids are rejected; and — the actual point of
the whole catalog — nothing here ever carries a raw score or a percentage."""

import re
import uuid

from app.models.artifact import Artifact, ArtifactType
from app.models.profile import AgeGroup
from app.services.report_narrative_context import (
    build_report_narrative_context,
    unknown_source_ids,
)
from app.services.report_narrative_context import _artifact_evidence, ONBOARDING_SOURCE_TYPES

_HAS_DIGIT = re.compile(r"\d")


def _artifact(value: str) -> Artifact:
    return Artifact(id=uuid.uuid4(), profile_id=uuid.uuid4(), type=ArtifactType.club, value=value)


def test_every_evidence_item_has_source_id_type_and_text() -> None:
    context = build_report_narrative_context(
        age_group=AgeGroup.senior,
        strengths=["R", "I"],
        personality_profile={"openness": 70.0, "conscientiousness": 30.0},
        personality_notes={"openness": "Тебе интересно узнавать новое", "conscientiousness": "..."},
        thinking_style={"creative_think": 80.0, "systematic": 20.0, "strategic": 60.0, "practical": 10.0},
        motivation_top=["interest", "creation"],
        motivation_highlights=[
            "Тебя больше всего драйвит — заниматься тем, что по-настоящему интересно",
            "Тебя больше всего драйвит — создавать что-то своё",
        ],
        subjects_liked=["Физика"],
        subjects_easy=["Литература"],
        artifacts=[_artifact("Робототехника")],
    )

    assert context.evidence, "should not be empty for this input"
    for item in context.evidence:
        assert item.source_id
        assert item.source_type
        assert item.text


def test_junior_context_has_mi_evidence_and_no_riasec_claims() -> None:
    context = build_report_narrative_context(
        age_group=AgeGroup.junior,
        strengths=["logical", "musical"],
        personality_profile={},
        personality_notes={},
        thinking_style={},
        motivation_top=[],
        motivation_highlights=[],
        subjects_liked=[],
        subjects_easy=[],
        artifacts=[],
    )

    assert context.interest_instrument == "mi"
    mi_items = [e for e in context.evidence if e.source_type == "mi_category"]
    assert {e.source_id for e in mi_items} == {"mi:logical", "mi:musical"}
    assert not any(e.source_type == "riasec_category" for e in context.evidence)
    assert not any(e.source_id.startswith("riasec:") for e in context.evidence)


def test_middle_senior_context_has_riasec_evidence() -> None:
    context = build_report_narrative_context(
        age_group=AgeGroup.middle,
        strengths=["R", "I"],
        personality_profile={},
        personality_notes={},
        thinking_style={},
        motivation_top=[],
        motivation_highlights=[],
        subjects_liked=[],
        subjects_easy=[],
        artifacts=[],
    )

    assert context.interest_instrument == "riasec"
    riasec_items = [e for e in context.evidence if e.source_type == "riasec_category"]
    assert {e.source_id for e in riasec_items} == {"riasec:R", "riasec:I"}
    assert not any(e.source_type == "mi_category" for e in context.evidence)


def test_harter_pairs_and_triplets_produce_identical_motivation_evidence_shape() -> None:
    """The catalog only ever sees motivation_top/motivation_highlights — it
    can't tell whether junior/middle's Harter pairs or senior's MOST/LEAST
    triplets produced them, and the resulting evidence must be identical
    either way for the same top/highlights values."""
    shared_kwargs = dict(
        personality_profile={}, personality_notes={}, thinking_style={},
        motivation_top=["interest", "helping"],
        motivation_highlights=[
            "Тебя больше всего драйвит — заниматься тем, что по-настоящему интересно",
            "Тебя больше всего драйвит — приносить пользу другим",
        ],
        subjects_liked=[], subjects_easy=[], artifacts=[],
    )

    junior_from_harter = build_report_narrative_context(age_group=AgeGroup.junior, strengths=[], **shared_kwargs)
    senior_from_triplets = build_report_narrative_context(age_group=AgeGroup.senior, strengths=[], **shared_kwargs)

    junior_motivation = [e for e in junior_from_harter.evidence if e.source_type == "motivation"]
    senior_motivation = [e for e in senior_from_triplets.evidence if e.source_type == "motivation"]
    assert junior_motivation == senior_motivation


def test_personality_evidence_only_includes_high_tier_traits() -> None:
    context = build_report_narrative_context(
        age_group=AgeGroup.senior,
        strengths=[],
        personality_profile={"openness": 75.0, "conscientiousness": 45.0, "agreeableness": 20.0},
        personality_notes={
            "openness": "высокая открытость",
            "conscientiousness": "средняя добросовестность",
            "agreeableness": "низкая доброжелательность",
        },
        thinking_style={},
        motivation_top=[], motivation_highlights=[],
        subjects_liked=[], subjects_easy=[], artifacts=[],
    )

    personality_items = [e for e in context.evidence if e.source_type == "personality"]
    assert {e.source_id for e in personality_items} == {"personality:openness"}


def test_thinking_style_evidence_picks_top_two_deterministically_on_ties() -> None:
    context = build_report_narrative_context(
        age_group=AgeGroup.senior,
        strengths=[],
        personality_profile={}, personality_notes={},
        # creative_think and systematic tie at 50 — fixed order must break the tie.
        thinking_style={"creative_think": 50.0, "systematic": 50.0, "strategic": 10.0, "practical": 10.0},
        motivation_top=[], motivation_highlights=[],
        subjects_liked=[], subjects_easy=[], artifacts=[],
    )

    thinking_items = [e for e in context.evidence if e.source_type == "thinking_style"]
    assert [e.source_id for e in thinking_items] == ["thinking_style:creative_think", "thinking_style:systematic"]


def test_thinking_style_evidence_omitted_when_there_is_no_real_signal() -> None:
    """No data (empty dict) or a genuine 0.0 for every category must not
    still hand out a confident-looking "top 2" — that would be a fact this
    catalog fabricated, not one it observed."""
    empty = build_report_narrative_context(
        age_group=AgeGroup.senior,
        strengths=[],
        personality_profile={}, personality_notes={},
        thinking_style={},
        motivation_top=[], motivation_highlights=[],
        subjects_liked=[], subjects_easy=[], artifacts=[],
    )
    all_zero = build_report_narrative_context(
        age_group=AgeGroup.senior,
        strengths=[],
        personality_profile={}, personality_notes={},
        thinking_style={"creative_think": 0.0, "systematic": 0.0, "strategic": 0.0, "practical": 0.0},
        motivation_top=[], motivation_highlights=[],
        subjects_liked=[], subjects_easy=[], artifacts=[],
    )

    assert not any(e.source_type == "thinking_style" for e in empty.evidence)
    assert not any(e.source_type == "thinking_style" for e in all_zero.evidence)


def test_thinking_style_evidence_includes_only_the_one_real_signal() -> None:
    """A partial signal (one non-zero category) must yield exactly that one
    item, not padded out to 2 with unmeasured categories."""
    context = build_report_narrative_context(
        age_group=AgeGroup.senior,
        strengths=[],
        personality_profile={}, personality_notes={},
        thinking_style={"creative_think": 40.0, "systematic": 0.0, "strategic": 0.0, "practical": 0.0},
        motivation_top=[], motivation_highlights=[],
        subjects_liked=[], subjects_easy=[], artifacts=[],
    )

    thinking_items = [e for e in context.evidence if e.source_type == "thinking_style"]
    assert [e.source_id for e in thinking_items] == ["thinking_style:creative_think"]


def test_unknown_source_ids_are_rejected() -> None:
    context = build_report_narrative_context(
        age_group=AgeGroup.senior,
        strengths=["R"],
        personality_profile={}, personality_notes={}, thinking_style={},
        motivation_top=[], motivation_highlights=[],
        subjects_liked=[], subjects_easy=[], artifacts=[],
    )

    rejected = unknown_source_ids(context, ["riasec:R", "riasec:Z", "made_up:thing"])

    assert rejected == {"riasec:Z", "made_up:thing"}


def test_evidence_contains_no_raw_numbers_or_percent_signs() -> None:
    """The actual point of the catalog: none of the *derived/categorical*
    evidence (interests, personality, motivation, thinking style — the
    labels this module itself writes) is a score. Free-text sources
    (subjects, artifacts — the student's own words, e.g. "3 года плавания")
    are exempt from this check on purpose: a digit there is real content,
    not a leaked score, and banning it would make honest input fragile."""
    context = build_report_narrative_context(
        age_group=AgeGroup.senior,
        strengths=["R", "I", "A"],
        personality_profile={
            "openness": 90.0, "conscientiousness": 85.0,
            "extraversion": 40.0, "agreeableness": 40.0, "emotional_stability": 40.0,
        },
        personality_notes={"openness": "Тебе интересно узнавать новое", "conscientiousness": "Ты организован"},
        thinking_style={"creative_think": 90.0, "systematic": 85.0, "strategic": 10.0, "practical": 5.0},
        motivation_top=["interest"],
        motivation_highlights=["Тебя больше всего драйвит — заниматься тем, что по-настоящему интересно"],
        subjects_liked=["Физика"],
        subjects_easy=["Литература"],
        artifacts=[_artifact("Робототехника, 2 года")],
    )

    derived_types = {"mi_category", "riasec_category", "personality", "motivation", "thinking_style"}
    derived_items = [e for e in context.evidence if e.source_type in derived_types]
    assert derived_items, "sanity check: this input should produce derived evidence"
    for item in derived_items:
        assert "%" not in item.text
        assert not _HAS_DIGIT.search(item.text), f"evidence text looks numeric: {item.text!r}"


def test_near_duplicate_artifacts_merge_into_one_evidence_item() -> None:
    """Found live: a student entered "Программирование" (hobby),
    "IT/программирование" (club) and "Робототехника" (hobby) as three
    separate artifacts — left ungrouped, each became its own strength card,
    reading as the same fact repeated three times. The first two share the
    word "программирование" and must merge; "Робототехника" shares no
    significant word with either and must stay separate."""
    artifacts = [
        _artifact("Программирование"),
        _artifact("Робототехника"),
        _artifact("IT/программирование"),
    ]

    evidence = _artifact_evidence(artifacts)

    assert len(evidence) == 2
    combined = next(e for e in evidence if ";" in e.text)
    assert "Программирование" in combined.text and "IT/программирование" in combined.text
    solo = next(e for e in evidence if e is not combined)
    assert solo.text == "Робототехника"


def test_unrelated_artifacts_are_never_merged() -> None:
    artifacts = [_artifact("Робототехника"), _artifact("Рисование"), _artifact("Волейбол")]

    evidence = _artifact_evidence(artifacts)

    assert len(evidence) == 3
    assert {e.text for e in evidence} == {"Робототехника", "Рисование", "Волейбол"}


def test_single_artifact_is_unaffected_by_grouping() -> None:
    evidence = _artifact_evidence([_artifact("Шахматы")])
    assert len(evidence) == 1
    assert evidence[0].text == "Шахматы"


def test_onboarding_evidence_is_capped_but_test_derived_evidence_is_not() -> None:
    """Found live: a student with 3 onboarding artifacts (all about
    programming/robotics) and only 1 RIASEC + 2 personality facts ended up
    with HALF their strength_cards about onboarding hobbies — and the
    careers shown (driven only by the RIASEC test) had nothing to do with
    those hobbies. Onboarding evidence (self-reported, not measured by the
    test) must never outnumber/crowd out what the test actually found."""
    context = build_report_narrative_context(
        age_group=AgeGroup.senior,
        strengths=["R", "I", "C"],  # 3 riasec_category items, never capped
        personality_profile={
            "openness": 90.0, "conscientiousness": 85.0,
            "extraversion": 40.0, "agreeableness": 40.0, "emotional_stability": 40.0,
        },
        personality_notes={"openness": "Тебе интересно новое", "conscientiousness": "Ты организован"},
        thinking_style={},
        motivation_top=[], motivation_highlights=[],
        subjects_liked=["Физика", "Химия"],
        subjects_easy=["Информатика"],
        artifacts=[_artifact("Программирование"), _artifact("Робототехника"), _artifact("Шахматы")],
    )

    onboarding_items = [e for e in context.evidence if e.source_type in ONBOARDING_SOURCE_TYPES]
    test_items = [e for e in context.evidence if e.source_type in ("riasec_category", "personality")]

    assert len(onboarding_items) == 2, "capped even though 5 onboarding facts were provided"
    assert len(test_items) == 5, "test-derived evidence (3 riasec + 2 personality) must never be capped"
