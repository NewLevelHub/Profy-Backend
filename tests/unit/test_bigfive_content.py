"""app/services/bigfive_content.py — `personality_notes_for_age()`, the
tier-lookup that feeds report_v2_assembler.build_personality_notes()
("Твой характер"). Pure function, no DB/LLM.
"""
from app.services.bigfive_content import (
    PERSONALITY_LABELS,
    _NOTES,
    _NOTES_JUNIOR,
    personality_notes_for_age,
)

_MID_PROFILE = {
    "openness": 50.0, "conscientiousness": 50.0, "extraversion": 50.0,
    "agreeableness": 50.0, "emotional_stability": 50.0,
}


def test_covers_all_five_traits():
    notes = personality_notes_for_age(False, _MID_PROFILE)
    assert set(notes) == set(PERSONALITY_LABELS)


def test_high_tier_boundary_is_inclusive():
    profile = {**_MID_PROFILE, "openness": 60.0}
    notes = personality_notes_for_age(False, profile)
    assert notes["openness"] == _NOTES["openness"]["high"]


def test_low_tier_boundary_is_inclusive():
    profile = {**_MID_PROFILE, "openness": 40.0}
    notes = personality_notes_for_age(False, profile)
    assert notes["openness"] == _NOTES["openness"]["low"]


def test_between_bounds_is_mid_tier():
    profile = {**_MID_PROFILE, "openness": 50.0}
    notes = personality_notes_for_age(False, profile)
    assert notes["openness"] == _NOTES["openness"]["mid"]


def test_adult_wording_for_middle_and_senior():
    notes = personality_notes_for_age(False, {**_MID_PROFILE, "conscientiousness": 80.0})
    assert notes["conscientiousness"] == _NOTES["conscientiousness"]["high"]
    assert notes["conscientiousness"] != _NOTES_JUNIOR["conscientiousness"]["high"]


def test_junior_gets_the_simplified_table_not_the_adult_one():
    notes = personality_notes_for_age(True, {**_MID_PROFILE, "conscientiousness": 80.0})
    assert notes["conscientiousness"] == _NOTES_JUNIOR["conscientiousness"]["high"]
    assert notes["conscientiousness"] != _NOTES["conscientiousness"]["high"]


def test_junior_table_covers_every_trait_and_tier():
    for trait in PERSONALITY_LABELS:
        assert trait in _NOTES_JUNIOR, f"{trait} missing from the junior table"
        for tier in ("high", "mid", "low"):
            assert tier in _NOTES_JUNIOR[trait], f"{trait}.{tier} missing from the junior table"
            assert _NOTES_JUNIOR[trait][tier]  # never blank


def test_junior_wording_has_no_abstractions_the_adult_table_uses():
    # A loose but meaningful proxy for "short and concrete" (TZ_Profi.md
    # §4.1): junior sentences must not be longer than the adult ones for
    # the same trait/tier — if this ever regresses to copy-pasting the
    # adult text, this catches it structurally, not just by inspection.
    for trait in PERSONALITY_LABELS:
        for tier in ("high", "mid", "low"):
            assert len(_NOTES_JUNIOR[trait][tier]) <= len(_NOTES[trait][tier])
