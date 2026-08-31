"""app/services/bigfive_content.py — `relative_bands()` (the per-trait tier,
now relative to the student's own five-trait average, not an absolute
cutoff) and `personality_notes_for_age()`, the tier-lookup that feeds
report_v2_assembler.build_personality_notes() ("Твой характер"). Pure
functions, no DB/LLM.
"""
from app.services.bigfive_content import (
    _FLAT_SPREAD,
    _NOTES,
    _NOTES_JUNIOR,
    _REL_BAND,
    PERSONALITY_LABELS,
    personality_notes_for_age,
    relative_bands,
    strength_phrases,
)

_MID_PROFILE = {
    "openness": 50.0, "conscientiousness": 50.0, "extraversion": 50.0,
    "agreeableness": 50.0, "emotional_stability": 50.0,
}


def _profile(**overrides: float) -> dict[str, float]:
    return {**_MID_PROFILE, **overrides}


# --- relative_bands --------------------------------------------------------

def test_flat_profile_is_all_medium() -> None:
    # spread 0 -> below _FLAT_SPREAD -> nothing is called out
    assert relative_bands(_MID_PROFILE) == {t: "medium" for t in _MID_PROFILE}


def test_spread_just_under_the_flat_threshold_is_still_all_medium() -> None:
    profile = _profile(openness=50.0 + _FLAT_SPREAD - 0.1)
    assert set(relative_bands(profile).values()) == {"medium"}


def test_trait_far_enough_above_own_mean_is_high_below_is_low() -> None:
    # one trait pulled up, one pulled down, past _REL_BAND from the mean
    profile = _profile(conscientiousness=95.0, openness=5.0)
    bands = relative_bands(profile)
    assert bands["conscientiousness"] == "high"
    assert bands["openness"] == "low"
    assert bands["extraversion"] == "medium"


def test_band_edge_is_measured_from_the_mean_not_from_fifty() -> None:
    # mean here is 60, so a trait at 68 (= mean + _REL_BAND) is exactly "high"
    profile = {
        "openness": 68.0, "conscientiousness": 68.0, "extraversion": 68.0,
        "agreeableness": 68.0, "emotional_stability": 28.0,
    }
    bands = relative_bands(profile)
    assert bands["openness"] == "high"          # 68 - 60 == _REL_BAND
    assert bands["emotional_stability"] == "low"


def test_empty_profile_returns_empty() -> None:
    assert relative_bands({}) == {}


# --- personality_notes_for_age (tier -> wording table) -------------------

def test_covers_all_five_traits() -> None:
    notes = personality_notes_for_age(False, _MID_PROFILE)
    assert set(notes) == set(PERSONALITY_LABELS)


def test_high_relative_trait_gets_the_high_note() -> None:
    notes = personality_notes_for_age(False, _profile(openness=95.0, conscientiousness=5.0))
    assert notes["openness"] == _NOTES["openness"]["high"]
    assert notes["conscientiousness"] == _NOTES["conscientiousness"]["low"]


def test_flat_profile_gets_the_mid_note_for_every_trait() -> None:
    notes = personality_notes_for_age(False, _MID_PROFILE)
    assert all(notes[t] == _NOTES[t]["mid"] for t in PERSONALITY_LABELS)


def test_adult_wording_for_middle_and_senior() -> None:
    notes = personality_notes_for_age(False, _profile(conscientiousness=90.0, openness=10.0))
    assert notes["conscientiousness"] == _NOTES["conscientiousness"]["high"]
    assert notes["conscientiousness"] != _NOTES_JUNIOR["conscientiousness"]["high"]


def test_junior_gets_the_simplified_table_not_the_adult_one() -> None:
    notes = personality_notes_for_age(True, _profile(conscientiousness=90.0, openness=10.0))
    assert notes["conscientiousness"] == _NOTES_JUNIOR["conscientiousness"]["high"]
    assert notes["conscientiousness"] != _NOTES["conscientiousness"]["high"]


def test_junior_table_covers_every_trait_and_tier() -> None:
    for trait in PERSONALITY_LABELS:
        assert trait in _NOTES_JUNIOR, f"{trait} missing from the junior table"
        for tier in ("high", "mid", "low"):
            assert tier in _NOTES_JUNIOR[trait], f"{trait}.{tier} missing from the junior table"
            assert _NOTES_JUNIOR[trait][tier]  # never blank


def test_junior_wording_has_no_abstractions_the_adult_table_uses() -> None:
    # A loose but meaningful proxy for "short and concrete": junior sentences
    # must not be longer than the adult ones for the same trait/tier — if this
    # ever regresses to copy-pasting the adult text, this catches it
    # structurally, not just by inspection.
    for trait in PERSONALITY_LABELS:
        for tier in ("high", "mid", "low"):
            assert len(_NOTES_JUNIOR[trait][tier]) <= len(_NOTES[trait][tier])


# --- strength_phrases (admin-only personality_highlights) ---------------

def test_strength_phrases_fire_only_for_high_relative_growth_traits() -> None:
    # openness + emotional_stability pulled high, conscientiousness low
    profile = _profile(openness=95.0, emotional_stability=90.0, conscientiousness=5.0)
    phrases = strength_phrases(profile)
    assert any("пробовать новое" in p for p in phrases)
    assert any("неудачи" in p for p in phrases)
    assert not any("до конца" in p for p in phrases)


def test_strength_phrases_empty_on_a_flat_profile() -> None:
    assert strength_phrases(_MID_PROFILE) == []
