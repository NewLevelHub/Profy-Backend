"""No DB/Redis — pure scoring math for app/services/bigfive_service.py:
the min-max normalization and the acquiescence (response-style) correction.
The query wiring (keying_counts / _grand_mean / raw_scores against real
rows) is exercised end-to-end by tests/integration/test_age_matrix_full_flow.py.
"""

from app.services import bigfive_service
from app.services.bigfive_service import _acquiescence_shift, _clamp


# --- min-max normalize -------------------------------------------------------

def test_normalize_floor_is_one_per_item_not_zero() -> None:
    counts = {"N": 24, "E": 24, "O": 24, "A": 24, "C": 24}
    # every item answered "1" -> raw == count -> 0%
    assert bigfive_service.normalize({d: 24.0 for d in counts}, counts) == {d: 0.0 for d in counts}


def test_normalize_midpoint_and_ceiling() -> None:
    counts = {"N": 10, "E": 10, "O": 10, "A": 10, "C": 10}
    # all "3" -> raw 30 -> 50% ; all "5" -> raw 50 -> 100%
    assert bigfive_service.normalize({d: 30.0 for d in counts}, counts)["N"] == 50.0
    assert bigfive_service.normalize({d: 50.0 for d in counts}, counts)["N"] == 100.0


def test_normalize_zero_questions_is_zero_not_division_error() -> None:
    assert bigfive_service.normalize({}, {"N": 0, "E": 4, "O": 4, "A": 4, "C": 4})["N"] == 0.0


def test_normalize_clamps_a_corrected_sum_past_the_theoretical_bounds() -> None:
    counts = {"N": 4, "E": 4, "O": 4, "A": 4, "C": 4}
    # corrected raw can land just outside [count, 5*count] for extreme responders
    assert bigfive_service.normalize({"N": 23.0, "E": 1.0, "O": 12.0, "A": 12.0, "C": 12.0}, counts)["N"] == 100.0
    assert bigfive_service.normalize({"N": 23.0, "E": 1.0, "O": 12.0, "A": 12.0, "C": 12.0}, counts)["E"] == 0.0


def test_clamp() -> None:
    assert _clamp(-5.0) == 0.0
    assert _clamp(150.0) == 100.0
    assert _clamp(47.9) == 47.9


# --- acquiescence correction ----------------------------------------------

def test_shift_is_zero_for_a_keyed_balanced_domain() -> None:
    # O is 12+/12- in the full bank -> no response-style leak to correct
    for mean in (1.0, 2.5, 3.0, 4.0, 5.0):
        assert _acquiescence_shift(minus_count=12, plus_count=12, mean_answer=mean) == 0.0


def test_shift_is_zero_when_the_respondent_answers_at_the_midpoint() -> None:
    assert _acquiescence_shift(minus_count=17, plus_count=7, mean_answer=3.0) == 0.0


def test_yea_sayer_is_lifted_on_a_minus_heavy_domain_and_lowered_on_a_plus_heavy_one() -> None:
    # Agreeableness: 7+/17- ; Neuroticism: 17+/7- ; mean answer 4.0 -> +/- 1.0
    assert _acquiescence_shift(minus_count=17, plus_count=7, mean_answer=4.0) == 10.0
    assert _acquiescence_shift(minus_count=7, plus_count=17, mean_answer=4.0) == -10.0


def test_nay_sayer_correction_is_the_mirror_image() -> None:
    assert _acquiescence_shift(minus_count=17, plus_count=7, mean_answer=2.0) == -10.0


def test_correction_meaningfully_moves_the_normalized_agreeableness_of_a_yea_sayer() -> None:
    counts = {"N": 24, "E": 24, "O": 24, "A": 24, "C": 24}
    uncorrected_A = 60.0  # a yea-sayer's reverse-keyed A sum sits low
    shift = _acquiescence_shift(minus_count=17, plus_count=7, mean_answer=4.0)  # +10.0

    before = bigfive_service.normalize({**{d: 60.0 for d in counts}}, counts)["A"]
    after = bigfive_service.normalize({**{d: 60.0 for d in counts}, "A": uncorrected_A + shift}, counts)["A"]

    assert before == 37.5
    assert after == 47.9
    assert after > before


def test_facet_normalize_shares_the_formula_and_the_clamp() -> None:
    counts = {("O", 1): 4, ("C", 2): 4}
    out = bigfive_service.facet_normalize({("O", 1): 12.0, ("C", 2): 25.0}, counts)
    assert out[("O", 1)] == 50.0   # raw 12 on 4 items -> mean 3 -> 50%
    assert out[("C", 2)] == 100.0  # raw 25 > theoretical max 20 -> clamped
