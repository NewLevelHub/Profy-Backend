import math
import uuid

import pytest

from app.models.akinator_question import AkinatorQuestion
from app.services.akinator_engine import age_variant_matches, match_score, reject_leaf, update_belief


def _question(age_variant: str) -> AkinatorQuestion:
    return AkinatorQuestion(
        id=uuid.uuid4(), kind="direct", depth=0, age_variant=age_variant,
        text="q", text_junior=None, options=[{"text": "opt", "axis_weights": {}}],
        resolves_pair=None, is_active=True, order=0,
    )


def test_match_score_sums_products_over_answer_axes_normalized_by_leaf_norm():
    """Calibration-pass-3 fix: raw dot product (People:2*2 + Data:1*0 = 4) is
    scaled down by the leaf's own profile norm (||{People:2,Care:1}|| =
    sqrt(5)) — see match_score's docstring for why (un-normalized, leaves
    with many strong axes always won regardless of actual fit)."""
    assert math.isclose(
        match_score({"People": 2, "Data": 1}, {"People": 2, "Care": 1}), 4.0 / math.sqrt(5)
    )
    assert match_score({}, {"People": 2}) == 0.0


def test_match_score_is_zero_for_an_empty_leaf_profile():
    """No profile to align with -> no signal, not a division-by-zero crash."""
    assert match_score({"People": 2}, {}) == 0.0


def test_update_belief_sums_to_one():
    """AC1: after an update, Σ belief ≈ 1.0."""
    belief = {"a": 1 / 3, "b": 1 / 3, "c": 1 / 3}
    profiles = {"a": {"People": 2}, "b": {"Data": 2}, "c": {"Ideas": 2}}

    result = update_belief(belief, {"People": 2}, profiles, beta=0.7)

    assert math.isclose(sum(result.values()), 1.0, abs_tol=1e-9)


def test_dont_know_is_identity():
    """AC2: "не знаю" (empty answer_weights) doesn't change belief."""
    belief = {"a": 0.5, "b": 0.3, "c": 0.2}
    profiles = {"a": {"People": 2}, "b": {"Data": 2}, "c": {"Ideas": 2}}

    result = update_belief(belief, {}, profiles, beta=0.7)

    assert result == belief


def test_strong_match_raises_that_leafs_belief_monotonically():
    """AC3: a leaf whose profile strongly matches the answer gains belief;
    an unrelated leaf loses relative share."""
    belief = {"a": 0.5, "b": 0.5}
    profiles = {
        "a": {"People": 2, "Care": 2},  # perfectly aligned with the answer
        "b": {"Data": 2, "Focus": 2},   # untouched by the answer's axes
    }

    result = update_belief(belief, {"People": 2, "Care": 2}, profiles, beta=0.7)

    assert result["a"] > belief["a"]
    assert result["b"] < belief["b"]
    assert result["a"] > result["b"]


def test_convergence_on_toy_catalog_of_5_leaves():
    """AC4: repeated answers pointing at one leaf converge belief onto it."""
    profiles = {
        "teacher": {"People": 2, "Dev": 2},
        "programmer": {"Data": 2, "Focus": 2, "People": -1},
        "artist": {"Ideas": 2, "Vis": 1},
        "surgeon": {"Care": 2, "Motor": 2, "Focus": 1},
        "accountant": {"Data": 2, "Struct": 2, "People": -1},
    }
    belief = dict.fromkeys(profiles, 1 / len(profiles))
    answer = {"Data": 2, "Focus": 2}  # strongly favors "programmer"

    previous_target_belief = belief["programmer"]
    for _ in range(15):
        belief = update_belief(belief, answer, profiles, beta=0.7)
        assert math.isclose(sum(belief.values()), 1.0, abs_tol=1e-9)
        assert belief["programmer"] >= previous_target_belief
        previous_target_belief = belief["programmer"]

    assert belief["programmer"] > 0.9
    assert max(belief, key=belief.get) == "programmer"


def test_reject_leaf_removes_it_and_renormalizes():
    """AC2 (reject ticket): rejecting a leaf drops it entirely and rescales
    the rest back to Σ=1, so it can never resurface via belief lookups."""
    belief = {"a": 0.6, "b": 0.25, "c": 0.15}

    result = reject_leaf(belief, "a")

    assert "a" not in result
    assert math.isclose(sum(result.values()), 1.0, abs_tol=1e-9)
    # relative proportions between the untouched leaves are preserved
    assert math.isclose(result["b"] / result["c"], 0.25 / 0.15, rel_tol=1e-9)


def test_reject_leaf_unknown_slug_raises():
    with pytest.raises(ValueError):
        reject_leaf({"a": 0.6, "b": 0.4}, "does-not-exist")


def test_reject_leaf_last_candidate_raises():
    """Rejecting the only remaining leaf leaves nothing to redistribute to."""
    with pytest.raises(ValueError):
        reject_leaf({"a": 1.0}, "a")


def test_middle_also_sees_senior_only_questions():
    """Calibration-pass fix: middle was meant to converge like senior, but
    with only age_variant="both" questions it never had enough signal to
    beat its ceiling — always fell back to a forced cluster. Sharing
    senior's question pool fixes this without new middle-specific content.
    junior deliberately keeps the smaller, softer pool."""
    both_q = _question("both")
    senior_q = _question("senior")
    junior_q = _question("junior")

    assert age_variant_matches(both_q, "middle") is True
    assert age_variant_matches(senior_q, "middle") is True
    assert age_variant_matches(junior_q, "middle") is False


def test_junior_does_not_gain_senior_only_questions():
    senior_q = _question("senior")
    assert age_variant_matches(senior_q, "junior") is False
