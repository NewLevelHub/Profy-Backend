import math
import random
import uuid
from collections import Counter

from app.models.akinator_question import AkinatorQuestion
from app.models.assessment_session import AssessmentSession
from app.services.akinator_engine import match_score, select_next_question, update_belief


def _question(*, depth, kind, axis, order, age_variant="both", options=None):
    return AkinatorQuestion(
        id=uuid.uuid4(),
        kind=kind,
        depth=depth,
        age_variant=age_variant,
        text=f"q-{order}",
        text_junior=None,
        options=options or [{"text": "opt", "axis_weights": {axis: 2}}],
        resolves_pair=None,
        is_active=True,
        order=order,
    )


def _session(*, step, asked_question_ids=None, asked_axis_families=None, belief=None):
    return AssessmentSession(
        id=uuid.uuid4(),
        assessment_id=uuid.uuid4(),
        belief=belief or {},
        asked_question_ids=asked_question_ids or [],
        asked_axis_families=asked_axis_families or [],
        step=step,
        status="in_progress",
    )


def test_early_steps_pick_direct_shallow_new_family_and_never_repeat_a_family():
    """AC1: steps 0/1/2 — depth<=1, direct, no repeated axis families."""
    q_people = _question(depth=0, kind="direct", axis="People", order=10)   # family A
    q_data = _question(depth=1, kind="direct", axis="Data", order=20)       # family A too
    q_care = _question(depth=1, kind="direct", axis="Care", order=30)       # family B
    q_focus_deep = _question(depth=2, kind="direct", axis="Focus", order=40)  # depth too high
    q_risk_situational = _question(depth=1, kind="situational", axis="Risk", order=50)  # wrong kind
    q_motor = _question(depth=0, kind="direct", axis="Motor", order=5)      # family C

    candidates = [q_people, q_data, q_care, q_focus_deep, q_risk_situational, q_motor]

    session = _session(step=0)
    first = select_next_question(session, candidates, leaf_profiles={}, age_group="senior")
    assert first is q_motor  # lowest order among eligible {q_people, q_data, q_care, q_motor}
    assert first.depth <= 1
    assert first.kind == "direct"

    session = _session(step=1, asked_question_ids=[q_motor.id], asked_axis_families=["C"])
    second = select_next_question(session, candidates, leaf_profiles={}, age_group="senior")
    assert second is q_people  # family A not asked yet, lowest order among {q_people, q_data, q_care}
    assert second.depth <= 1
    assert second.kind == "direct"

    session = _session(
        step=2,
        asked_question_ids=[q_motor.id, q_people.id],
        asked_axis_families=["C", "A"],
    )
    third = select_next_question(session, candidates, leaf_profiles={}, age_group="senior")
    assert third is q_care  # only family B (Care) left unasked among eligible depth<=1 direct
    assert third.depth <= 1
    assert third.kind == "direct"

    chosen_families = {"C", "A", "B"}
    assert len(chosen_families) == 3  # each step introduced a brand-new family


def test_wide_start_accepts_a_question_that_also_touches_an_already_asked_family():
    """Calibration-pass fix: real depth<=1 direct questions almost always
    straddle multiple families (e.g. People+Care in one question) — the old
    `isdisjoint` rule rejected any candidate touching *any* already-asked
    family, even if it also introduced a brand-new one, collapsing the
    3-step wide start down to just 1 real step. A candidate should now be
    picked as long as it introduces >=1 new family, overlap allowed.

    q_mixed (order=1, families A+B — A already asked) has a lower order than
    q_pure_new (order=2, family C only, fully new). Under the old strict
    `isdisjoint` rule q_mixed would be rejected outright, leaving q_pure_new
    as the only wide candidate. Under the relaxed rule both qualify and
    q_mixed wins on order — proving the relaxation actually changed which
    question gets picked, not just that *a* question got picked."""
    q_mixed = _question(  # family A (already asked) + family B (new) in one question
        depth=1, kind="direct", axis="People", order=1,
        options=[{"text": "opt", "axis_weights": {"People": 1, "Care": 2}}],
    )
    q_pure_new = _question(depth=0, kind="direct", axis="Motor", order=2)  # family C, fully new

    session = _session(step=1, asked_question_ids=[uuid.uuid4()], asked_axis_families=["A"])
    selected = select_next_question(
        session, [q_mixed, q_pure_new], leaf_profiles={}, age_group="senior"
    )

    assert selected is q_mixed  # old isdisjoint rule would have picked q_pure_new instead


def test_step_3_or_later_picks_minimum_expected_posterior_entropy():
    """AC2: brute-force check that the chosen question minimizes expected
    posterior entropy on a toy 2-leaf scenario. Selection is a weighted
    random pick (calibration pass 2), not a strict argmin, so this pins
    temperature near zero to make the pick deterministic for the check."""
    leaf_profiles = {"a": {"Focus": 2}, "b": {"Focus": -2}}
    belief = {"a": 0.5, "b": 0.5}
    beta = 0.7

    discriminating = _question(
        depth=2, kind="situational", axis="Focus", order=1,
        options=[
            {"text": "x", "axis_weights": {"Focus": 2}},
            {"text": "y", "axis_weights": {"Focus": -2}},
        ],
    )
    useless = _question(
        depth=2, kind="situational", axis="Risk", order=2,
        options=[
            {"text": "x", "axis_weights": {"Risk": 2}},
            {"text": "y", "axis_weights": {"Risk": -2}},
        ],
    )  # neither leaf carries "Risk" -> match is 0 for every option/leaf combo

    def brute_force_expected_entropy(question) -> float:
        options_weights = [opt["axis_weights"] for opt in question.options]

        def option_probs_for_leaf(profile):
            scores = [beta * match_score(w, profile) for w in options_weights]
            m = max(scores)
            exps = [math.exp(s - m) for s in scores]
            total = sum(exps)
            return [e / total for e in exps]

        probs_by_leaf = {leaf: option_probs_for_leaf(p) for leaf, p in leaf_profiles.items()}
        option_probs = [
            sum(belief[leaf] * probs_by_leaf[leaf][i] for leaf in belief)
            for i in range(len(options_weights))
        ]

        expected = 0.0
        for i, weights in enumerate(options_weights):
            posterior = update_belief(belief, weights, leaf_profiles, beta)
            entropy = -sum(p * math.log(p) for p in posterior.values() if p > 0)
            expected += option_probs[i] * entropy
        return expected

    entropies = {
        "discriminating": brute_force_expected_entropy(discriminating),
        "useless": brute_force_expected_entropy(useless),
    }
    assert entropies["discriminating"] < entropies["useless"]  # sanity: the toy scenario is meaningful

    session = _session(step=3, belief=belief)
    selected = select_next_question(
        session, [discriminating, useless], leaf_profiles, age_group="senior",
        beta=beta, temperature=1e-6,
    )

    assert selected is discriminating


def test_question_selection_is_probabilistic_not_strict_argmin():
    """Calibration-pass fix: real session logs showed strict argmin made a
    handful of questions "the best" for nearly every session regardless of
    the user's own answers — about half the 45-question bank was picked in
    under 15 of ~3000 real sessions. Selection is now a weighted random pick
    (favoring lower expected entropy, per _sample_by_entropy) instead of
    always the single minimum, so the less-informative candidate must still
    get picked sometimes across many draws at the default temperature."""
    leaf_profiles = {"a": {"Focus": 2}, "b": {"Focus": -2}}
    belief = {"a": 0.5, "b": 0.5}
    beta = 0.7

    discriminating = _question(
        depth=2, kind="situational", axis="Focus", order=1,
        options=[
            {"text": "x", "axis_weights": {"Focus": 2}},
            {"text": "y", "axis_weights": {"Focus": -2}},
        ],
    )
    useless = _question(
        depth=2, kind="situational", axis="Risk", order=2,
        options=[
            {"text": "x", "axis_weights": {"Risk": 2}},
            {"text": "y", "axis_weights": {"Risk": -2}},
        ],
    )

    session = _session(step=3, belief=belief)
    rng = random.Random(1234)
    picks = Counter()
    for _ in range(200):
        selected = select_next_question(
            session, [discriminating, useless], leaf_profiles, age_group="senior",
            beta=beta, rng=rng,
        )
        picks[selected.order] += 1

    assert picks[discriminating.order] > picks[useless.order]  # still favors the better question
    assert picks[useless.order] > 0  # but not exclusively — this is the whole fix
