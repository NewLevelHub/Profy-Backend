"""No DB/Redis involved — pure-function scoring math, the cheapest layer to
verify. Also serves as the infra smoke test for anything that doesn't need
`db_session`/`client` (no event loop surprises, no fixtures required)."""

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
    """Found live: Архивариус/Аудитор/Бухгалтер (all "CSE") and Директор по
    логистике ("ESC")/HR-менеджер ("SEC") all scored identically for a
    {C,S,E}-topped student under the old `letter in direction_code`
    membership check — every anagram of the same 3 letters tied. Positional
    weighting must break that: matching the student's own code order
    exactly scores strictly higher than any reshuffled permutation, and
    different permutations score differently from each other."""
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
