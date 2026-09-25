"""PRO-427 — pure АСТУР scoring: percents, spatial scale, knowledge profile,
numeric-series gap, quick instructions and protocol quality."""
from app.services.astur.scoring import AttemptInput, score_attempt
from app.services.astur.scoring_rules import LEGACY_SCORING_VERSION, get_rules
from tests.astur_fixtures import attempt_input, content_answers, quick_entries, v1_bank

BANK = v1_bank()
RULES = get_rules("2")
FULL_TIMINGS = {s.key: 60_000 for s in BANK.subtests if s.key != "lability"}


def _attempt(answers: dict, lability: dict | None = None, **overrides) -> AttemptInput:
    return attempt_input(BANK, answers, lability, **overrides)


def _subtest(snapshot, key):
    return next(s for s in snapshot.subtests if s.key == key)


def _item(key: str, index: int = 0) -> dict:
    return BANK.subtest(key).items[index]


# ── per-subtest percents and the overall ────────────────────────────────────


def test_all_correct_gives_100_percent_everywhere_with_score_over_max() -> None:
    snap = score_attempt(BANK, _attempt(content_answers(BANK)), RULES)
    assert {s.key: (s.score, s.max_score, s.percent) for s in snap.subtests} == {
        "awareness": (20, 20, 100.0), "analogies": (16, 16, 100.0), "classification": (12, 12, 100.0),
        "generalization": (38, 38, 100.0), "logical_schemas": (26, 26, 100.0),
        "numeric_series": (15, 15, 100.0), "geometric_figures": (5, 5, 100.0),
    }
    assert snap.overall_percent == 100.0
    assert snap.age_at_completion == 16 and snap.grade_at_completion == 10
    assert snap.scoring_version == "2" and snap.bank_version == 1


def test_overall_is_an_equal_weight_mean_of_subtest_percents() -> None:
    # Wrong on the 38-point generalization and on the 5-point figures: equal
    # weight means both cost the same 1/7 of the overall.
    snap = score_attempt(BANK, _attempt(content_answers(BANK, wrong={"generalization"})), RULES)
    snap_figures = score_attempt(BANK, _attempt(content_answers(BANK, wrong={"geometric_figures"})), RULES)
    assert snap.overall_percent == snap_figures.overall_percent == round(600 / 7, 1)


def test_quick_instructions_never_enter_the_overall() -> None:
    all_wrong_quick = quick_entries(BANK, correct_positions=set())
    snap = score_attempt(BANK, _attempt(content_answers(BANK), all_wrong_quick), RULES)
    assert snap.overall_percent == 100.0


def test_geometric_figures_are_scored_as_spatial_and_counted_in_v2_only() -> None:
    answers = content_answers(BANK, wrong={"geometric_figures"})
    current = score_attempt(BANK, _attempt(answers), RULES)
    legacy = score_attempt(BANK, _attempt(answers, legacy=True), get_rules(LEGACY_SCORING_VERSION))

    assert _subtest(current, "geometric_figures").percent == 0.0
    assert _subtest(current, "geometric_figures").in_overall is True
    assert _subtest(legacy, "geometric_figures").in_overall is False
    assert current.overall_percent < 100.0
    assert legacy.overall_percent == 100.0


def test_item_scores_are_keyed_by_stable_item_id() -> None:
    snap = score_attempt(BANK, _attempt(content_answers(BANK)), RULES)
    assert snap.item_scores["generalization-01"] == 2
    assert snap.item_scores["geometric_figures-05"] == 1
    assert len(snap.item_scores) == 95


# ── item matching ───────────────────────────────────────────────────────────


def test_choice_matching_ignores_case_whitespace_and_punctuation() -> None:
    answers = content_answers(BANK)
    answers["awareness"]["1"] = "  " + _item("awareness")["answer"]["ru"].upper() + ". "
    snap = score_attempt(BANK, _attempt(answers), RULES)
    assert _subtest(snap, "awareness").score == 20


def test_open_answers_score_by_tier_with_typo_tolerance() -> None:
    answers = content_answers(BANK)
    answers["generalization"]["1"] = _item("generalization")["score_1"]["ru"][0]
    # "устное народное творчество" with a dropped final letter.
    answers["generalization"]["2"] = "устное народное творчеств"
    answers["generalization"]["3"] = "что-то совсем другое"
    snap = score_attempt(BANK, _attempt(answers), RULES)
    assert snap.item_scores["generalization-01"] == 1
    assert snap.item_scores["generalization-02"] == 2
    assert snap.item_scores["generalization-03"] == 0


def test_chain_scores_one_point_per_restored_adjacent_link() -> None:
    concepts = _item("logical_schemas")["concepts"]["ru"]  # 5 concepts → 4 links
    answers = content_answers(BANK)
    answers["logical_schemas"]["1"] = [concepts[1], concepts[0], concepts[2], concepts[3], concepts[4]]
    snap = score_attempt(BANK, _attempt(answers), RULES)
    assert snap.item_scores["logical_schemas-01"] == 2  # 2→3 and 3→4 survive


def test_number_pair_accepts_numeric_strings_but_needs_both_in_order() -> None:
    first, second = _item("numeric_series")["answer"]
    answers = content_answers(BANK)
    answers["numeric_series"]["1"] = [str(first), str(second)]
    answers["numeric_series"]["2"] = list(reversed(_item("numeric_series", 1)["answer"]))
    snap = score_attempt(BANK, _attempt(answers), RULES)
    assert snap.item_scores["numeric_series-01"] == 1
    assert snap.item_scores["numeric_series-02"] == 0


def test_malformed_answers_score_zero_instead_of_raising() -> None:
    answers = content_answers(BANK)
    answers["classification"]["1"] = "not a list"
    answers["numeric_series"]["1"] = ["x", None]
    answers["logical_schemas"]["1"] = {"bad": 1}
    snap = score_attempt(BANK, _attempt(answers), RULES)
    assert snap.item_scores["classification-01"] == 0
    assert snap.item_scores["numeric_series-01"] == 0
    assert snap.item_scores["logical_schemas-01"] == 0


# ── knowledge profile ───────────────────────────────────────────────────────


def _answers_with_subject_misses(misses: dict[str, int]) -> dict:
    """All correct, then blank-free wrong answers on the first N tagged items
    of each subject (awareness first, then generalization)."""
    answers = content_answers(BANK)
    remaining = dict(misses)
    for key in ("awareness", "generalization"):
        for i, item in enumerate(BANK.subtest(key).items, start=1):
            if remaining.get(item["subject"], 0) > 0:
                answers[key][str(i)] = "неверно"
                remaining[item["subject"]] -= 1
    return answers


def test_tie_between_areas_is_a_mixed_profile_not_the_first_area_in_code() -> None:
    snap = score_attempt(BANK, _attempt(content_answers(BANK)), RULES)
    assert snap.subject_profile.status == "mixed"
    assert snap.subject_profile.leading is None


def test_one_item_never_decides_the_leading_area() -> None:
    # physics_math (9 items) leads by a single item: humanities 17/18, natural
    # 11/12. The gap to the runner-up (5.6 pp) is far below the threshold
    # scaled to the smaller area — 2 items of 9 = 22.2 pp.
    snap = score_attempt(
        BANK, _attempt(_answers_with_subject_misses({"humanities": 1, "natural_science": 1})), RULES
    )
    assert snap.subject_profile.status == "mixed"
    assert snap.subject_profile.threshold_pp == 22.2


def test_leading_area_needs_the_size_scaled_threshold() -> None:
    # humanities 18 items, natural_science 12: humanities 100%, natural 75%,
    # physics_math 66.7% → leader gap 25 pp vs threshold max(15, 2/12) = 16.7.
    snap = score_attempt(
        BANK, _attempt(_answers_with_subject_misses({"natural_science": 3, "physics_math": 3})), RULES
    )
    profile = snap.subject_profile
    assert profile.status == "leading"
    assert profile.leading == "humanities"
    assert profile.runner_up == "natural_science"
    assert profile.threshold_pp == 16.7


def test_profile_areas_are_percentages_of_their_own_size() -> None:
    snap = score_attempt(BANK, _attempt(content_answers(BANK)), RULES)
    sizes = {a.key: a.item_count for a in snap.subject_profile.areas}
    assert sizes == {"humanities": 18, "physics_math": 9, "natural_science": 12}


def test_missing_required_answers_give_insufficient_data() -> None:
    answers = content_answers(BANK)
    for i, item in enumerate(BANK.subtest("awareness").items, start=1):
        if item["subject"] == "physics_math":
            answers["awareness"][str(i)] = ""
    snap = score_attempt(BANK, _attempt(answers), RULES)
    assert snap.subject_profile.status == "insufficient_data"


# ── numeric series next to physics/math knowledge ───────────────────────────


def test_math_divergence_is_reported_when_gap_reaches_threshold() -> None:
    snap = score_attempt(BANK, _attempt(content_answers(BANK, wrong={"numeric_series"})), RULES)
    math = snap.math_reasoning
    assert math.numeric_series_percent == 0.0
    assert math.physics_math_knowledge_percent == 100.0
    assert math.divergence == "knowledge_higher"
    assert math.threshold_pp == 20

    aligned = score_attempt(BANK, _attempt(content_answers(BANK)), RULES)
    assert aligned.math_reasoning.divergence == "none"


# ── quick instructions ──────────────────────────────────────────────────────


def test_quick_instructions_report_halves_on_observed_data() -> None:
    lability = quick_entries(BANK, correct_positions={1, 2, 3, 4, 5})
    quick = score_attempt(BANK, _attempt(content_answers(BANK), lability), RULES).quick_instructions
    assert quick.status == "ok"
    assert (quick.first_half_correct, quick.second_half_correct) == (4, 1)
    assert (quick.first_half_percent, quick.second_half_percent) == (100.0, 25.0)
    assert quick.accuracy_change_pp == -75.0
    assert quick.median_ms == 1500


def test_late_commands_do_not_count_as_correct_and_are_flagged() -> None:
    lability = quick_entries(BANK, over_limit_positions={8})
    snap = score_attempt(BANK, _attempt(content_answers(BANK), lability), RULES)
    assert snap.quick_instructions.on_time == 7
    assert snap.quick_instructions.second_half_correct == 3
    codes = {f.code for f in snap.protocol_quality.flags}
    assert "quick_over_limit" in codes
    assert snap.protocol_quality.ok is False


def test_fewer_than_6_on_time_commands_skips_the_halves_comparison() -> None:
    lability = quick_entries(BANK, over_limit_positions={1, 2, 3})
    quick = score_attempt(BANK, _attempt(content_answers(BANK), lability), RULES).quick_instructions
    assert quick.status == "insufficient_on_time"
    assert quick.accuracy_change_pp is None
    assert quick.first_half_percent is None


def test_zero_to_zero_is_just_zero_change_not_a_stability_verdict() -> None:
    lability = quick_entries(BANK, correct_positions=set())
    quick = score_attempt(BANK, _attempt(content_answers(BANK), lability), RULES).quick_instructions
    assert (quick.first_half_percent, quick.second_half_percent, quick.accuracy_change_pp) == (0.0, 0.0, 0.0)
    assert set(type(quick).model_fields) >= {"status", "accuracy_change_pp"}
    assert "fatigue" not in type(quick).model_fields


def test_own_name_command_follows_the_first_letter_of_the_first_name() -> None:
    from app.services.astur.scoring import _own_name_expected

    assert _own_name_expected("Аружан Абенова", ["да", "нет"]) == "да"
    assert _own_name_expected("Данияр Ким", ["да", "нет"]) == "нет"
    assert _own_name_expected("Өмір Сейітов", ["иә", "жоқ"]) == "иә"


# ── protocol quality ────────────────────────────────────────────────────────


def test_clean_protocol_is_ok() -> None:
    snap = score_attempt(BANK, _attempt(content_answers(BANK)), RULES)
    assert snap.protocol_quality.ok is True
    assert snap.protocol_quality.flags == []


def test_missing_timing_overtime_and_blanks_are_flagged() -> None:
    answers = content_answers(BANK)
    answers["analogies"] = {str(i): "" for i in range(1, 17)}
    timings = dict(FULL_TIMINGS)
    timings.pop("awareness")
    timings["numeric_series"] = (BANK.subtest("numeric_series").time_limit_sec + 60) * 1000
    snap = score_attempt(BANK, _attempt(answers, subtest_timings_ms=timings), RULES)
    flags = {(f.code, f.subtest) for f in snap.protocol_quality.flags}
    assert ("subtest_timing_missing", "awareness") in flags
    assert ("subtest_over_time", "numeric_series") in flags
    assert ("many_blank_answers", "analogies") in flags


def test_legacy_attempt_is_marked_and_carries_no_age() -> None:
    snap = score_attempt(
        BANK,
        _attempt(content_answers(BANK), legacy=True, age=None, grade=None, subtest_timings_ms={}),
        get_rules(LEGACY_SCORING_VERSION),
    )
    codes = {f.code for f in snap.protocol_quality.flags}
    assert snap.legacy is True
    assert snap.scoring_version == LEGACY_SCORING_VERSION
    assert {"legacy_protocol", "legacy_day_of_week_estimated"} <= codes
    assert "subtest_timing_missing" not in codes
    assert snap.age_at_completion is None


def test_latin_first_name_is_judged_by_its_letter_from_v3_on() -> None:
    from app.services.astur.scoring import _own_name_expected

    for name in ("Arman Seitov", "Aigerim", "Yana"):
        assert _own_name_expected(name, ["да", "нет"]) == "да"
    assert _own_name_expected("Timur", ["да", "нет"]) == "нет"
    # v2 behaviour is kept for snapshots it produced.
    assert _own_name_expected("Arman", ["да", "нет"], latin_vowels=False) == "нет"


def test_own_name_command_scoring_depends_on_the_rules_version() -> None:
    item_position = next(
        i for i, item in enumerate(BANK.subtest("lability").items, start=1) if item.get("dynamic") == "own_name"
    )
    lability = quick_entries(BANK)
    lability[str(item_position)]["answer"] = "да"  # "Arman" starts with a vowel
    attempt = _attempt(content_answers(BANK), lability, profile_name="Arman")

    v3 = score_attempt(BANK, attempt, get_rules("3")).quick_instructions
    v2 = score_attempt(BANK, attempt, get_rules("2")).quick_instructions
    assert v3.first_half_correct + v3.second_half_correct == 8
    assert v2.first_half_correct + v2.second_half_correct == 7
