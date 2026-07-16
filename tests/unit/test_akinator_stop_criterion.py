from app.config import settings
from app.services.akinator_engine import check_stop


def test_clear_leader_reveals_single():
    """AC1: top1 > T and top1 >= M * top2 -> reveal_single."""
    belief = {"a": 0.6, "b": 0.2, "c": 0.2}

    decision = check_stop(belief, step=5, age_group="senior")

    assert decision.status == "reveal_single"
    assert decision.leaves == ["a"]
    assert decision.reason == "confidence"


def test_two_close_leaders_reveal_cluster():
    """AC2: leaders too close for a single verdict -> cluster, k<=3, ~70%."""
    belief = {"a": 0.46, "b": 0.40, "c": 0.14}

    decision = check_stop(belief, step=5, age_group="senior")

    assert decision.status == "reveal_cluster"
    assert decision.reason == "confidence"
    assert len(decision.leaves) <= 3
    assert sum(belief[leaf] for leaf in decision.leaves) >= settings.AKINATOR_STOP_CLUSTER_THRESHOLD


def test_ceiling_with_flat_belief_reveals_cluster_not_an_error():
    """AC3: hitting the age ceiling with spread-out belief still reveals a
    cluster (valid outcome), never raises and never leaves "continue"."""
    belief = {"a": 0.2, "b": 0.2, "c": 0.2, "d": 0.2, "e": 0.2}

    decision = check_stop(belief, step=settings.AKINATOR_CEILING_SENIOR, age_group="senior")

    assert decision.status == "reveal_cluster"
    assert decision.reason == "ceiling"
    assert len(decision.leaves) <= 3


def test_confident_belief_is_blocked_until_all_axis_families_are_covered():
    """Calibration-pass fix: a leaf could previously win reveal_single purely
    on family A/B/C/D answers, without a single question ever probing family
    E (Math/Living/PhysSt/Acad) — e.g. "does this surgeon candidate actually
    like biology/math". asked_families gates both confidence branches."""
    belief = {"a": 0.6, "b": 0.2, "c": 0.2}  # would reveal_single without the gate

    incomplete = check_stop(belief, step=5, age_group="senior", asked_families={"A", "B"})
    assert incomplete.status == "continue"

    complete = check_stop(belief, step=5, age_group="senior", asked_families={"A", "B", "C", "D", "E"})
    assert complete.status == "reveal_single"
    assert complete.leaves == ["a"]


def test_ceiling_overrides_incomplete_family_coverage():
    """The age ceiling is a safety net: it must still force a reveal even if
    the question bank never managed to cover every axis family."""
    belief = {"a": 0.2, "b": 0.2, "c": 0.2, "d": 0.2, "e": 0.2}

    decision = check_stop(
        belief, step=settings.AKINATOR_CEILING_SENIOR, age_group="senior", asked_families={"A"}
    )

    assert decision.status == "reveal_cluster"
    assert decision.reason == "ceiling"


def test_asked_families_none_disables_the_gate():
    """Backward-compatible default: omitting asked_families (None) behaves
    exactly like before the calibration pass — no family-coverage gating."""
    belief = {"a": 0.6, "b": 0.2, "c": 0.2}

    decision = check_stop(belief, step=5, age_group="senior")

    assert decision.status == "reveal_single"


def test_junior_ceiling_is_lower_than_senior_ceiling():
    """AC4: the same flat belief and step count stops earlier for junior
    than for senior, per the settings-defined ceilings."""
    assert settings.AKINATOR_CEILING_JUNIOR < settings.AKINATOR_CEILING_SENIOR

    belief = {"a": 0.2, "b": 0.2, "c": 0.2, "d": 0.2, "e": 0.2}
    step = settings.AKINATOR_CEILING_JUNIOR  # reached junior's ceiling, not senior's

    junior_decision = check_stop(belief, step=step, age_group="junior")
    senior_decision = check_stop(belief, step=step, age_group="senior")

    assert junior_decision.status == "reveal_cluster"
    assert junior_decision.reason == "ceiling"
    assert senior_decision.status == "continue"
