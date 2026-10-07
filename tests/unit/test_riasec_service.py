"""No DB/Redis involved — pure-function scoring math, the cheapest layer to
verify. Also serves as the infra smoke test for anything that doesn't need
`db_session`/`client` (no event loop surprises, no fixtures required)."""

import pytest

from app.models.direction import Direction
from app.services import riasec_service


def test_normalize_scales_to_percent_of_maximum() -> None:
    raw = {"R": 10, "I": 0, "A": 15, "S": 0, "E": 0, "C": 0}
    counts = {"R": 4, "I": 4, "A": 3, "S": 4, "E": 4, "C": 4}

    normalized = riasec_service.normalize(raw, counts)

    # R: 10 / (4*5) * 100 = 50.0 ; A: 15 / (3*5) * 100 = 100.0 (answered max every time)
    assert normalized["R"] == 50.0
    assert normalized["A"] == 100.0
    assert normalized["I"] == 0.0


def test_normalize_treats_zero_questions_as_zero_not_division_error() -> None:
    normalized = riasec_service.normalize({}, {"R": 0, "I": 4, "A": 4, "S": 4, "E": 4, "C": 4})
    assert normalized["R"] == 0.0


def test_top_code_breaks_ties_by_fixed_holland_order() -> None:
    # R and I tie at 80.0 — HOLLAND_ORDER = ["R", "I", "A", "S", "E", "C"],
    # so R must win the tie deterministically, not depend on dict iteration.
    normalized = {"R": 80.0, "I": 80.0, "A": 50.0, "S": 20.0, "E": 10.0, "C": 5.0}
    assert riasec_service.top_code(normalized, limit=2) == ["R", "I"]


def test_differentiation_is_spread_between_max_and_min() -> None:
    normalized = {"R": 90.0, "I": 60.0, "A": 40.0, "S": 30.0, "E": 20.0, "C": 10.0}
    assert riasec_service.differentiation(normalized) == 80.0


def test_consistency_high_for_adjacent_types_on_the_hexagon() -> None:
    # R and I are adjacent on the RIASEC hexagon (distance 1) -> "high"
    assert riasec_service.consistency(["R", "I"]) == "high"


def test_consistency_low_for_opposite_types_on_the_hexagon() -> None:
    # R and S sit opposite each other (distance 3) -> "low"
    assert riasec_service.consistency(["R", "S"]) == "low"


def test_strengths_always_reaches_limit_even_when_aversion_disqualifies_most() -> None:
    """Found live: a student with >=30% explicit dislike on 5 of 6 RIASEC
    types ended up with 0-1 "strengths" — which collapsed the "Сильные
    стороны" section on the report to near-empty/empty. `strengths` must
    always reach `limit` (when there are enough categories to draw from at
    all), padding with the next best-scoring types regardless of aversion —
    career matching (top_code) already ignores aversion entirely, so this
    just brings the evidence catalog in line with that."""
    normalized = {"R": 60.0, "I": 55.0, "A": 50.0, "S": 70.0, "E": 45.0, "C": 40.0}
    # Every type except S disqualified (>=30% aversion).
    aversion_counts = {"R": 9, "I": 8, "A": 13, "S": 6, "E": 13, "C": 10}
    counts = {"R": 24, "I": 23, "A": 26, "S": 23, "E": 24, "C": 26}

    strengths, _ = riasec_service.strengths_weaknesses(normalized, aversion_counts, counts, limit=3)

    assert len(strengths) == 3
    assert "S" in strengths  # the one that legitimately passed the filter, still included
    assert len(set(strengths)) == 3  # no duplicates from the padding pass


def test_strengths_no_padding_needed_when_filter_already_yields_enough() -> None:
    normalized = {"R": 90.0, "I": 80.0, "A": 70.0, "S": 10.0, "E": 5.0, "C": 5.0}
    aversion_counts = {"R": 0, "I": 0, "A": 0, "S": 0, "E": 0, "C": 0}
    counts = {"R": 24, "I": 23, "A": 26, "S": 23, "E": 24, "C": 26}

    strengths, _ = riasec_service.strengths_weaknesses(normalized, aversion_counts, counts, limit=3)

    assert strengths == ["R", "I", "A"]


def test_strengths_pad_from_medium_band_when_nothing_clears_the_high_bar() -> None:
    """An ordinary profile with no type at LEVEL_HIGH_MIN still fills
    `strengths` to `limit` from the LEVEL_MEDIUM_MIN..LEVEL_HIGH_MIN band, by
    rank — so "Сильные стороны" isn't empty just because the absolute scale
    is demanding. (Before: this returned 0 strengths.)"""
    normalized = {"R": 68.0, "I": 64.0, "A": 58.0, "S": 52.0, "E": 40.0, "C": 30.0}
    aversion_counts = {t: 0 for t in "RIASEC"}
    counts = {t: 24 for t in "RIASEC"}

    strengths, _ = riasec_service.strengths_weaknesses(normalized, aversion_counts, counts, limit=3)

    assert strengths == ["R", "I", "A"]


def test_strengths_never_promotes_a_below_medium_type() -> None:
    """The floor the padding must not cross: a type below LEVEL_MEDIUM_MIN is
    "low" in interest_map, so it can never be cited as a strength — even when
    that leaves fewer than `limit` (I=A=100, everything else at 20 → only 2)."""
    normalized = {"I": 100.0, "A": 100.0, "R": 20.0, "C": 20.0, "E": 20.0, "S": 20.0}
    aversion_counts = {t: 0 for t in "RIASEC"}
    counts = {t: 24 for t in "RIASEC"}

    strengths, _ = riasec_service.strengths_weaknesses(normalized, aversion_counts, counts, limit=3)

    assert strengths == ["I", "A"]


def test_direction_letter_weight_rewards_the_directions_primary_letter_most() -> None:
    assert riasec_service.direction_letter_weight("C", "CSE") == 3
    assert riasec_service.direction_letter_weight("S", "CSE") == 2
    assert riasec_service.direction_letter_weight("E", "CSE") == 1
    assert riasec_service.direction_letter_weight("R", "CSE") == 0  # absent


def test_career_match_score_differentiates_anagrams_of_the_same_letters() -> None:
    """Legacy positional fallback must still break anagrams of the same
    3 letters (CSE/ESC/SEC/...) — used for the few directions without an
    O*NET vector (PRO-385)."""
    user_code = ["C", "S", "E"]

    exact = riasec_service.career_match_score(user_code, "CSE")
    esc = riasec_service.career_match_score(user_code, "ESC")
    sec = riasec_service.career_match_score(user_code, "SEC")
    ces = riasec_service.career_match_score(user_code, "CES")

    assert exact > esc
    assert exact > sec
    assert exact > ces
    assert len({exact, esc, sec, ces}) == 4  # all four permutations score differently


def test_career_match_score_zero_when_no_letters_overlap() -> None:
    assert riasec_service.career_match_score(["C", "S", "E"], "RIA") == 0


def test_pearson_correlation_perfect_and_opposite() -> None:
    profile = {"R": 10.0, "I": 20.0, "A": 30.0, "S": 40.0, "E": 50.0, "C": 60.0}
    assert riasec_service.pearson_correlation(profile, profile) == pytest.approx(1.0)
    opposite = {"R": 60.0, "I": 50.0, "A": 40.0, "S": 30.0, "E": 20.0, "C": 10.0}
    assert riasec_service.pearson_correlation(profile, opposite) == pytest.approx(-1.0)


def test_pearson_correlation_flat_profile_is_zero_not_nan() -> None:
    flat = {t: 50.0 for t in "RIASEC"}
    varying = {"R": 10.0, "I": 20.0, "A": 30.0, "S": 40.0, "E": 50.0, "C": 60.0}
    assert riasec_service.pearson_correlation(flat, varying) == 0.0


def test_pearson_azat_regression_ranks_pedagogue_above_financial_analyst() -> None:
    """Live case from PRO-385: Azat's profile used to get «Финансовый
    аналитик» as top-1 under 3-letter code ranking (C beat I by 0.04pp).
    Pearson on the full 6-dim vectors puts his real profession
    «Педагог-психолог» in the top-10 and the analyst near the bottom."""
    import json
    from pathlib import Path

    # Exact Likert sums / question counts from the ticket (before round-1).
    azat = {
        "R": 52 / (24 * 5) * 100,
        "I": 61 / (23 * 5) * 100,
        "A": 61 / (26 * 5) * 100,
        "S": 91 / (23 * 5) * 100,
        "E": 55 / (24 * 5) * 100,
        "C": 69 / (26 * 5) * 100,
    }
    data = json.loads(
        (Path(__file__).resolve().parents[2] / "scripts/data/our_professions_onet_riasec.json")
        .read_text(encoding="utf-8")
    )
    ranked = sorted(
        ((riasec_service.pearson_correlation(azat, entry["vec"]), entry["title"]) for entry in data),
        reverse=True,
    )
    by_title = {title: (i + 1, r) for i, (r, title) in enumerate(ranked)}

    ped_rank, ped_r = by_title["Педагог-психолог"]
    fin_rank, fin_r = by_title["Финансовый аналитик"]

    assert ped_rank <= 10
    assert ped_r == pytest.approx(0.888, abs=0.01)
    assert fin_rank > 50
    assert fin_r < 0.0
    assert ranked[0][1] == "Социальный работник"


def test_direction_match_score_uses_pearson_when_vector_present() -> None:
    direction = Direction(
        name={"ru": "Педагог"},
        slug="test-pedagog",
        holland_code="SIA",
        onet_vector={"R": 1.0, "I": 2.0, "A": 3.0, "S": 7.0, "E": 2.0, "C": 2.0},
    )
    normalized = {"R": 10.0, "I": 20.0, "A": 30.0, "S": 90.0, "E": 20.0, "C": 20.0}
    score = riasec_service.direction_match_score(normalized, direction)
    assert score == round(riasec_service.pearson_correlation(normalized, direction.onet_vector), 4)


def test_direction_match_score_falls_back_to_code_when_vector_missing() -> None:
    direction = Direction(name={"ru": "Военный"}, slug="test-voennyy", holland_code="RES")
    normalized = {"R": 90.0, "I": 10.0, "A": 10.0, "S": 20.0, "E": 80.0, "C": 10.0}
    # top_code = R, E, S → exact match with RES → 14/14 = 1.0
    assert riasec_service.direction_match_score(normalized, direction) == 1.0
