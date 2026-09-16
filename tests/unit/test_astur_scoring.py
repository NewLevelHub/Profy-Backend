"""PRO-338 Ф3.5 — astur_scoring.py: 6 scored subtests, СПН-group, the
recommended-profile pooling, and lability accuracy-by-half. Pure functions,
no DB (mirrors test_belbin_interpretation.py's convention)."""
from datetime import datetime, timezone

from app.services import astur_scoring
from scripts.astur_bank import (
    ANALOGIES_ITEMS,
    AWARENESS_ITEMS,
    CLASSIFICATION_ITEMS,
    GENERALIZATION_ITEMS,
    LABILITY_ITEMS,
    LOGICAL_SCHEMA_ITEMS,
    NUMERIC_SERIES_ITEMS,
)


def _all_correct_awareness() -> dict[str, str]:
    return {str(i): item["answer"] for i, item in enumerate(AWARENESS_ITEMS, start=1)}


def _all_correct_classification() -> dict[str, list[str]]:
    return {str(i): item["answer"] for i, item in enumerate(CLASSIFICATION_ITEMS, start=1)}


def _all_correct_generalization(*, tier: str = "score_2") -> dict[str, str]:
    return {str(i): item[tier][0] for i, item in enumerate(GENERALIZATION_ITEMS, start=1)}


def _all_correct_logical_schemas() -> dict[str, list[str]]:
    return {str(i): item["concepts"] for i, item in enumerate(LOGICAL_SCHEMA_ITEMS, start=1)}


def _all_correct_numeric_series() -> dict[str, list[int]]:
    return {str(i): item["answer"] for i, item in enumerate(NUMERIC_SERIES_ITEMS, start=1)}


def test_awareness_scoring_is_case_and_whitespace_insensitive() -> None:
    item = AWARENESS_ITEMS[0]
    assert astur_scoring._score_mc(item, item["answer"].upper()) == 1
    assert astur_scoring._score_mc(item, f"  {item['answer']}  ") == 1
    assert astur_scoring._score_mc(item, "точно не то") == 0
    assert astur_scoring._score_mc(item, None) == 0


def test_classification_requires_exactly_the_2_key_words_in_any_order() -> None:
    item = CLASSIFICATION_ITEMS[0]  # дог, спаниель
    assert astur_scoring._score_classification(item, list(reversed(item["answer"]))) == 1
    assert astur_scoring._score_classification(item, [item["answer"][0], "стол"]) == 0
    assert astur_scoring._score_classification(item, item["answer"] + ["extra"]) == 0
    assert astur_scoring._score_classification(item, "not a list") == 0


def test_generalization_scores_0_1_2_by_tier() -> None:
    item = GENERALIZATION_ITEMS[0]  # Ель-сосна
    assert astur_scoring._score_generalization(item, item["score_2"][0]) == 2
    assert astur_scoring._score_generalization(item, item["score_1"][0].upper()) == 1
    assert astur_scoring._score_generalization(item, "совершенно левый ответ") == 0
    assert astur_scoring._score_generalization(item, "") == 0


def test_logical_schema_awards_partial_credit_per_adjacent_link() -> None:
    item = LOGICAL_SCHEMA_ITEMS[0]  # 5 concepts, 4 possible links
    correct = item["concepts"]
    assert astur_scoring._score_logical_schema(item, correct) == 4

    # Swap the first two — breaks link 0 (a-b) and link 1 (b-c) since b's
    # neighbors both change, but link 2 and 3 survive untouched.
    swapped = [correct[1], correct[0]] + correct[2:]
    assert astur_scoring._score_logical_schema(item, swapped) == 2

    assert astur_scoring._score_logical_schema(item, "not a list") == 0


def test_numeric_series_requires_both_numbers_correct_and_ordered() -> None:
    item = NUMERIC_SERIES_ITEMS[0]  # answer [14, 16]
    assert astur_scoring._score_numeric_series(item, [14, 16]) == 1
    assert astur_scoring._score_numeric_series(item, ["14", "16"]) == 1  # string coercion
    assert astur_scoring._score_numeric_series(item, [16, 14]) == 0  # order matters
    assert astur_scoring._score_numeric_series(item, [14]) == 0
    assert astur_scoring._score_numeric_series(item, ["x", "y"]) == 0


def test_score_subtests_only_scores_whats_present() -> None:
    subtest_scores, raw_score = astur_scoring.score_subtests(
        {"awareness": _all_correct_awareness()}
    )
    assert subtest_scores == {"awareness": 20}
    assert raw_score == 20


def test_score_subtests_all_correct_hits_max_raw_score() -> None:
    answers = {
        "awareness": _all_correct_awareness(),
        "analogies": {str(i): item["answer"] for i, item in enumerate(ANALOGIES_ITEMS, start=1)},
        "classification": _all_correct_classification(),
        "generalization": _all_correct_generalization(),
        "logical_schemas": _all_correct_logical_schemas(),
        "numeric_series": _all_correct_numeric_series(),
    }
    subtest_scores, raw_score = astur_scoring.score_subtests(answers)
    assert raw_score == astur_scoring.MAX_RAW_SCORE == 127
    assert set(subtest_scores.keys()) == {
        "awareness", "analogies", "classification", "generalization",
        "logical_schemas", "numeric_series",
    }


def test_recommended_profile_is_empty_before_either_subtest_is_answered() -> None:
    assert astur_scoring.compute_recommended_profile({}) == {}


def test_recommended_profile_pools_awareness_and_generalization_by_subject() -> None:
    answers = {
        "awareness": _all_correct_awareness(),
        "generalization": _all_correct_generalization(),
    }
    profile = astur_scoring.compute_recommended_profile(answers)
    assert set(profile["shares"].keys()) == {"humanities", "physics_math", "natural_science"}
    # Every item answered correctly -> every subject's pooled fraction is 1.0.
    assert all(share == 1.0 for share in profile["shares"].values())
    assert profile["recommended"] in profile["shares"]


def test_lability_never_attempted_returns_none_none() -> None:
    assert astur_scoring.score_lability({}, submitted_at=datetime.now(timezone.utc), profile_name="Т") == (None, None)


def test_lability_static_items_score_against_hand_verified_keys() -> None:
    lability_answers = {
        "1": {"answer": "1"}, "3": {"answer": "плюс"}, "4": {"answer": "8"},
        "5": {"answer": "да"}, "7": {"answer": "крестик"}, "8": {"answer": "ниже"},
        # Dynamic items (2, 6) omitted from correctness assertions below —
        # covered by their own tests.
        "2": {"answer": "quadrat-not-checked"}, "6": {"answer": "x-not-checked"},
    }
    first_half, second_half = astur_scoring.score_lability(
        lability_answers, submitted_at=datetime(2026, 1, 5, tzinfo=timezone.utc),  # a Monday
        profile_name="Аружан Абенова",
    )
    # Items 1-4 (first half): 1,3,4 correct by construction; item 2 is
    # dynamic and very unlikely to accidentally match "quadrat-not-checked".
    assert first_half == 3 / 4
    # Items 5-8 (second half): 5,7,8 correct; item 6 dynamic, unlikely match.
    assert second_half == 3 / 4


def test_lability_day_of_week_dynamic_item_resolves_against_submission_date() -> None:
    # 2026-01-05 is a Monday ("понедельник" starts with "п", a consonant) -> квадрат.
    monday = datetime(2026, 1, 5, tzinfo=timezone.utc)
    lability_answers = {str(i): {"answer": ""} for i in range(1, 9)}
    lability_answers["2"] = {"answer": "квадрат"}

    first_half, _ = astur_scoring.score_lability(lability_answers, submitted_at=monday, profile_name="Т")
    assert first_half == 1 / 4  # only item 2 correct among items 1-4


def test_lability_own_name_dynamic_item_uses_first_and_last_word_heuristic() -> None:
    # "Аружан Абенова" -> first name starts with "А" (a vowel) -> expected "а".
    lability_answers = {str(i): {"answer": ""} for i in range(1, 9)}
    lability_answers["6"] = {"answer": "а"}

    _, second_half = astur_scoring.score_lability(
        lability_answers, submitted_at=datetime.now(timezone.utc), profile_name="Аружан Абенова",
    )
    assert second_half == 1 / 4  # only item 6 correct among items 5-8


def test_is_fatigue_signal_flags_drops_over_25_percent_only() -> None:
    assert astur_scoring.is_fatigue_signal(1.0, 0.76) is False
    assert astur_scoring.is_fatigue_signal(1.0, 0.74) is True
    assert astur_scoring.is_fatigue_signal(0.5, 0.6) is False  # improved, not a drop


def test_score_run_bundles_everything_and_spn_group_is_none_when_unscored() -> None:
    result = astur_scoring.score_run({}, {}, submitted_at=datetime.now(timezone.utc), profile_name="Т")
    assert result.raw_score == 0
    assert result.spn_group is None
    assert result.recommended_profile == {}
    assert result.lability_first_half_accuracy is None


def test_lability_item_count_matches_the_content_bank() -> None:
    assert len(LABILITY_ITEMS) == 8
