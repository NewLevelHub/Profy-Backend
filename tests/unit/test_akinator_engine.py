import math

from app.services.akinator_engine import match_score, update_belief


def test_match_score_sums_products_over_answer_axes():
    assert match_score({"People": 2, "Data": 1}, {"People": 2, "Care": 1}) == 4.0
    assert match_score({}, {"People": 2}) == 0.0


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
