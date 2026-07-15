"""Belief update + next-question selection for the axis-driven Akinator engine.

Pure math — no AI, no DB. See akinatorLogic/profi_axes_phase1.md ("Формула
апдейта", "Правило старта"):
    match(A, L) = Σ_ось A[ось] · L[ось]
    log belief(L) += β · match(A, L), затем softmax-нормировка (Σ belief = 1)
    Первые ~3 вопроса — широкие прямые по разным семействам (анти-жадность);
    дальше — минимизация ожидаемой постериорной энтропии, той же match-функцией.
"""
import math
from dataclasses import dataclass, field
from typing import Literal

from app.config import settings
from app.core.axes import AXIS_CATALOG, AxisFamily
from app.models.akinator_question import AkinatorQuestion
from app.models.assessment_session import AssessmentSession

# "первые ~3 вопроса" from profi_axes_phase1.md — not tunable via settings,
# it's a structural rule of the start, not a calibration knob like beta.
WIDE_START_STEPS = 3

_AXIS_FAMILY: dict[str, AxisFamily] = {axis.code: axis.family for axis in AXIS_CATALOG}


def match_score(answer_weights: dict[str, int], leaf_profile: dict[str, int]) -> float:
    """Σ over the answer's axes of weight * leaf's value on that axis (0 if the
    leaf doesn't carry that axis). Both dicts are sparse — only non-zero axes."""
    return float(sum(weight * leaf_profile.get(axis, 0) for axis, weight in answer_weights.items()))


def _log(prob: float) -> float:
    return -math.inf if prob <= 0 else math.log(prob)


def _softmax(log_values: dict[str, float]) -> dict[str, float]:
    max_log = max(log_values.values())
    exp_values = {leaf: math.exp(v - max_log) for leaf, v in log_values.items()}
    total = sum(exp_values.values())
    return {leaf: v / total for leaf, v in exp_values.items()}


def update_belief(
    belief: dict[str, float],
    answer_weights: dict[str, int],
    leaf_profiles: dict[str, dict[str, int]],
    beta: float | None = None,
) -> dict[str, float]:
    """Return the new belief after one answer. `belief` keys are leaf slugs and
    must be a valid probability distribution (Σ ≈ 1, all > 0).

    "Не знаю" is an empty `answer_weights` dict — identity, belief unchanged."""
    if not answer_weights:
        return dict(belief)

    beta = settings.AKINATOR_BETA if beta is None else beta
    log_belief = {
        leaf: _log(prob) + beta * match_score(answer_weights, leaf_profiles[leaf])
        for leaf, prob in belief.items()
    }
    return _softmax(log_belief)


def reject_leaf(belief: dict[str, float], leaf_slug: str) -> dict[str, float]:
    """Condition belief on "not leaf_slug": drop it entirely and renormalize
    the rest proportionally, so it can never resurface in this session (a
    stronger, permanent version of update_belief's usual nudge — see
    akinator_session_service.reject_leaf for the "ребёнок отверг" flow,
    distinct from the engine's own uncertainty in check_stop's cluster case).
    """
    if leaf_slug not in belief:
        raise ValueError(f"leaf {leaf_slug!r} is not a candidate in this belief")

    remaining_mass = 1.0 - belief[leaf_slug]
    if remaining_mass <= 1e-9:
        raise ValueError("no remaining candidates after rejecting this leaf")

    return {
        leaf: prob / remaining_mass for leaf, prob in belief.items() if leaf != leaf_slug
    }


def question_axis_families(question: AkinatorQuestion) -> set[AxisFamily]:
    """Every axis family touched by any of the question's answer options.

    Public: also used by akinator_session_service to append to
    session.asked_axis_families after an answer is recorded."""
    return {
        _AXIS_FAMILY[axis_code]
        for option in question.options
        for axis_code in option.get("axis_weights", {})
    }


def age_variant_matches(question: AkinatorQuestion, age_group: str) -> bool:
    """Public: also used by akinator_session_service to validate that a
    submitted answer's question actually belongs to this session's age group."""
    return question.age_variant == "both" or question.age_variant == age_group


def _is_wide_start_candidate(question: AkinatorQuestion, asked_families: set[str]) -> bool:
    if question.depth > 1 or question.kind != "direct":
        return False
    return question_axis_families(question).isdisjoint(asked_families)


def _entropy(belief: dict[str, float]) -> float:
    return -sum(prob * math.log(prob) for prob in belief.values() if prob > 0)


def _option_choice_probs(
    options_weights: list[dict[str, int]], leaf_profile: dict[str, int], beta: float
) -> list[float]:
    """P(leaf picks option i), softmax over beta * match_score per option — the
    same match/softmax machinery as update_belief, applied over options instead
    of over leaves (per "Та же match-функция" in the source doc)."""
    scores = [beta * match_score(weights, leaf_profile) for weights in options_weights]
    max_score = max(scores)
    exp_scores = [math.exp(score - max_score) for score in scores]
    total = sum(exp_scores)
    return [value / total for value in exp_scores]


def _expected_posterior_entropy(
    question: AkinatorQuestion,
    belief: dict[str, float],
    leaf_profiles: dict[str, dict[str, int]],
    beta: float,
) -> float:
    """E[entropy(belief after this question)], averaging each option's
    probability over the current belief (per "P(вариант) усредняем по
    текущему belief" in the source doc)."""
    options_weights = [option.get("axis_weights", {}) for option in question.options]
    option_probs_by_leaf = {
        leaf: _option_choice_probs(options_weights, leaf_profiles[leaf], beta) for leaf in belief
    }
    option_probs = [
        sum(belief[leaf] * option_probs_by_leaf[leaf][i] for leaf in belief)
        for i in range(len(options_weights))
    ]

    expected = 0.0
    for i, weights in enumerate(options_weights):
        if option_probs[i] <= 0:
            continue
        posterior = update_belief(belief, weights, leaf_profiles, beta)
        expected += option_probs[i] * _entropy(posterior)
    return expected


def select_next_question(
    session: AssessmentSession,
    candidate_questions: list[AkinatorQuestion],
    leaf_profiles: dict[str, dict[str, int]],
    age_group: str,
    beta: float | None = None,
) -> AkinatorQuestion | None:
    """Pick the next question for this session.

    step < WIDE_START_STEPS (anti-greedy start): depth ≤ 1, kind="direct",
    covering only axis families not yet in session.asked_axis_families — ties
    broken by `order` (the curated "Широкий старт" sequence).

    step >= WIDE_START_STEPS: argmin expected posterior entropy over the
    candidates, using the same match/softmax machinery as update_belief.

    Deviates from the ticket's one-line signature by taking `leaf_profiles`
    and `age_group` explicitly: neither entropy nor age eligibility can be
    computed from `session`/`candidate_questions` alone. Excludes questions
    already in session.asked_question_ids and ones that don't match age_group
    (age_variant="both" is always eligible). Returns None only if nothing at
    all qualifies (the bank has genuinely run dry for this session).
    """
    beta = settings.AKINATOR_BETA if beta is None else beta
    # asked_question_ids round-trips through JSONB as plain strings (UUID
    # objects aren't JSON-serializable) — compare both sides as strings.
    asked_ids = {str(qid) for qid in (session.asked_question_ids or [])}
    candidates = [
        q for q in candidate_questions
        if str(q.id) not in asked_ids and age_variant_matches(q, age_group)
    ]
    if not candidates:
        return None

    if session.step < WIDE_START_STEPS:
        asked_families = set(session.asked_axis_families or [])
        wide_candidates = [c for c in candidates if _is_wide_start_candidate(c, asked_families)]
        if wide_candidates:
            return min(wide_candidates, key=lambda q: q.order)
        # Real question banks rarely have many single-family shallow direct
        # questions (most early "what do you enjoy" questions touch several
        # families at once) — running out of untouched-family wide candidates
        # is normal, not a sign the whole bank is exhausted. Fall through to
        # entropy-based selection over the general candidate pool instead.

    return min(
        candidates,
        key=lambda q: _expected_posterior_entropy(q, session.belief, leaf_profiles, beta),
    )


_AGE_CEILINGS: dict[str, str] = {
    "junior": "AKINATOR_CEILING_JUNIOR",
    "middle": "AKINATOR_CEILING_MIDDLE",
    "senior": "AKINATOR_CEILING_SENIOR",
}


def _age_ceiling(age_group: str) -> int:
    return getattr(settings, _AGE_CEILINGS[age_group])


@dataclass(frozen=True, slots=True)
class StopDecision:
    status: Literal["continue", "reveal_single", "reveal_cluster"]
    leaves: list[str] = field(default_factory=list)
    reason: Literal["confidence", "ceiling"] | None = None


def _top_cluster(
    sorted_leaves: list[tuple[str, float]], k: int, threshold: float
) -> tuple[list[str], float]:
    """Greedily take leaves off the (belief-descending) list, stopping once
    either the cumulative probability crosses `threshold` or `k` are taken —
    whichever comes first."""
    cluster: list[str] = []
    cumulative = 0.0
    for leaf, prob in sorted_leaves[:k]:
        cluster.append(leaf)
        cumulative += prob
        if cumulative >= threshold:
            break
    return cluster, cumulative


def check_stop(
    belief: dict[str, float],
    step: int,
    age_group: str,
    *,
    t: float | None = None,
    m: float | None = None,
    cluster_k: int | None = None,
    cluster_threshold: float | None = None,
) -> StopDecision:
    """Decide whether to stop and what to reveal, per profi_axes_phase1.md
    "Критерий остановки":
      - single leaf if top1 > T and top1 >= M * top2 (confident winner);
      - else a cluster of <= cluster_k leaves once their cumulative belief
        reaches cluster_threshold (close race, but a small group stands out);
      - else continue — unless the age-based question ceiling is reached, in
        which case a cluster is forced regardless of how flat belief still is
        (a valid outcome, never an error).
    """
    t = settings.AKINATOR_STOP_T if t is None else t
    m = settings.AKINATOR_STOP_M if m is None else m
    cluster_k = settings.AKINATOR_STOP_CLUSTER_K if cluster_k is None else cluster_k
    cluster_threshold = (
        settings.AKINATOR_STOP_CLUSTER_THRESHOLD if cluster_threshold is None else cluster_threshold
    )

    sorted_leaves = sorted(belief.items(), key=lambda item: item[1], reverse=True)
    top1_leaf, top1_prob = sorted_leaves[0]
    top2_prob = sorted_leaves[1][1] if len(sorted_leaves) > 1 else 0.0

    if top1_prob > t and top1_prob >= m * top2_prob:
        return StopDecision(status="reveal_single", leaves=[top1_leaf], reason="confidence")

    cluster, cluster_prob = _top_cluster(sorted_leaves, cluster_k, cluster_threshold)
    if cluster_prob >= cluster_threshold:
        return StopDecision(status="reveal_cluster", leaves=cluster, reason="confidence")

    if step >= _age_ceiling(age_group):
        return StopDecision(status="reveal_cluster", leaves=cluster, reason="ceiling")

    return StopDecision(status="continue")
