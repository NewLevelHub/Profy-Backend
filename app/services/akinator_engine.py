"""Belief update + next-question selection for the axis-driven Akinator engine.

Pure math — no AI, no DB. See akinatorLogic/profi_axes_phase1.md ("Формула
апдейта", "Правило старта"):
    match(A, L) = Σ_ось A[ось] · L[ось], normalized by ||L|| (calibration pass
    3 — see match_score's docstring: un-normalized, leaves with many strong
    axes always won regardless of fit)
    log belief(L) += β · match(A, L), затем softmax-нормировка (Σ belief = 1)
    Первые ~3 вопроса — широкие прямые по разным семействам (анти-жадность);
    дальше — минимизация ожидаемой постериорной энтропии, той же match-функцией.
"""
import math
import random
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
    """Alignment between an answer and a leaf's profile: raw dot product
    (Σ weight * leaf's value per axis, 0 if the leaf doesn't carry that axis),
    scaled down by the leaf's own profile norm.

    Without that scaling (calibration pass 3), leaves with many strong
    (magnitude-2) axes systematically won regardless of whether they were
    the right answer — a census of one "textbook" persona per real
    profession found 41/67 losing to the same ~10 "loud" profiles (paramedic,
    surgeon, programmer, accountant, architect, ...) more often than not.
    Dividing by ||leaf_profile|| makes the score reflect how much of *that
    leaf's own* signature the answer explains, not the leaf's raw volume —
    a quiet, narrow profile (coach, barista) can now compete on equal footing
    with a loud, broad one for an answer that genuinely fits it best."""
    raw = sum(weight * leaf_profile.get(axis, 0) for axis, weight in answer_weights.items())
    norm = math.sqrt(sum(value * value for value in leaf_profile.values()))
    return float(raw) / norm if norm else 0.0


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


class NoRemainingCandidatesError(ValueError):
    """Raised when rejecting a leaf (or a batch of them) would empty the
    belief entirely — distinct from an unknown-slug ValueError: this is a
    legitimate terminal state ("the user rejected everything left"), not a
    client error, so callers should catch it separately (see
    akinator_session_service._reject_and_advance)."""


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
        raise NoRemainingCandidatesError("no remaining candidates after rejecting this leaf")

    return {
        leaf: prob / remaining_mass for leaf, prob in belief.items() if leaf != leaf_slug
    }


def reject_leaves(belief: dict[str, float], slugs: list[str]) -> dict[str, float]:
    """Batch version of reject_leaf — drop several leaves at once (e.g. "none
    of these fit" rejecting every card on the current reveal in one go).
    Sequential single rejects-and-renormalizes are equivalent to dropping the
    whole set and renormalizing once, so this just loops reject_leaf, reusing
    its renormalization, its ValueError on an unknown slug, and its
    "no remaining candidates" ValueError for the case where the batch would
    empty the belief entirely."""
    for slug in slugs:
        belief = reject_leaf(belief, slug)
    return belief


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
    submitted answer's question actually belongs to this session's age group.

    "middle" also gets "senior"-tagged questions (calibration pass): with
    only the ~31 age_variant="both" questions, middle sessions never had
    enough signal to reach a confident single answer within their ceiling —
    always bottomed out at "reveal_cluster via ceiling", same as junior.
    junior staying cluster-only there is intentional (softer outcome for
    younger ages); middle was meant to behave like senior, so it now shares
    senior's full question pool instead of getting new middle-specific
    content."""
    if question.age_variant == "both" or question.age_variant == age_group:
        return True
    return age_group == "middle" and question.age_variant == "senior"


def _is_wide_start_candidate(question: AkinatorQuestion, asked_families: set[str]) -> bool:
    """Eligible if it introduces at least one axis family not yet asked about.

    Was `isdisjoint` (every touched family had to be brand new) — but real
    depth<=1 direct questions almost always straddle multiple families (e.g.
    People+Focus+Data in one question), so requiring full disjointness left
    only the very first wide-start question eligible: everything after it
    touched family A (already asked) and got rejected outright, collapsing
    the "first 3 steps are wide" rule down to just 1 real wide step. `issubset`
    only rejects a question that brings zero new information (every family it
    touches has already been covered)."""
    if question.depth > 1 or question.kind != "direct":
        return False
    return not question_axis_families(question).issubset(asked_families)


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


def _sample_by_entropy(
    candidates: list[AkinatorQuestion],
    entropies: list[float],
    temperature: float,
    rng: random.Random,
) -> AkinatorQuestion:
    """Weighted-random pick over candidates, favoring lower expected posterior
    entropy (more informative) without always picking the single minimum.

    Same softmax shape as update_belief/_option_choice_probs, but over
    -entropy/temperature instead of beta*match_score: low temperature ~=
    strict argmin (deterministic), high temperature ~= uniform random. Fixes
    a real UX bug (see AKINATOR_QUESTION_TEMPERATURE in config.py) — strict
    argmin made a handful of sharply-worded resolves_pair questions "the
    best" for nearly every session regardless of the user's own answers,
    leaving roughly half the question bank never selected in practice.
    """
    min_entropy = min(entropies)
    scores = [-(e - min_entropy) / temperature for e in entropies]
    max_score = max(scores)
    weights = [math.exp(s - max_score) for s in scores]
    return rng.choices(candidates, weights=weights, k=1)[0]


# Soft, non-exclusive nudge toward resolves_pair questions whose named leaves
# overlap the CURRENT top-N belief — see select_next_question's docstring for
# why this replaces the earlier hard-filter attempt (measured worse: 12->10
# failing vs 12->7 with no filter at all, because excluding a resolver
# outright could permanently lock a leaf out of its own best rescue chance).
# This only shifts the softmax odds in _sample_by_entropy; every candidate,
# relevant or not, stays selectable.
_RELEVANCE_BONUS = 0.15
_RELEVANCE_ONSET_STEP = 6
_RELEVANCE_TOP_N = 5


def _relevance_bonus(question: AkinatorQuestion, belief: dict[str, float], top_n: int) -> float:
    """Entropy discount applied to a resolves_pair question when at least one
    of its named leaves is currently plausible (top `top_n` by belief) —
    makes it more likely, not certain, to be picked over an equally-
    informative but currently-irrelevant resolver. Non-resolver questions
    (resolves_pair=None) get no bonus; they were never the problem."""
    pair = question.resolves_pair
    if not pair:
        return 0.0
    top_slugs = {slug for slug, _ in sorted(belief.items(), key=lambda kv: -kv[1])[:top_n]}
    return _RELEVANCE_BONUS if any(slug in top_slugs for slug in pair) else 0.0


def select_next_question(
    session: AssessmentSession,
    candidate_questions: list[AkinatorQuestion],
    leaf_profiles: dict[str, dict[str, int]],
    age_group: str,
    beta: float | None = None,
    temperature: float | None = None,
    rng: random.Random | None = None,
) -> AkinatorQuestion | None:
    """Pick the next question for this session.

    step < WIDE_START_STEPS (anti-greedy start): depth ≤ 1, kind="direct",
    covering only axis families not yet in session.asked_axis_families — ties
    broken by `order` (the curated "Широкий старт" sequence, deterministic
    by design — every session starts the same way on purpose).

    step >= WIDE_START_STEPS: weighted-random pick favoring minimum expected
    posterior entropy (see _sample_by_entropy), using the same match/softmax
    machinery as update_belief. Not a strict argmin — see
    AKINATOR_QUESTION_TEMPERATURE. From step >= _RELEVANCE_ONSET_STEP, a
    small entropy discount (_relevance_bonus) nudges the sampling toward
    resolves_pair questions relevant to the current top _RELEVANCE_TOP_N
    belief, without excluding anything else — see that function's docstring.

    (An earlier attempt at this same idea used a hard filter instead of a
    soft nudge — excluded irrelevant resolves_pair questions outright rather
    than just discounting their entropy. Measured worse (calibration
    playtest pass, 2026-07): against the same 38-profession census (n=30,
    seed=7), the resolves_pair weight-balance fixes alone dropped failing
    professions 12->7, but the hard filter on top made it *worse*, 12->10
    (tried top_n=5 and top_n=10; both underperformed no filter) — excluding
    a resolver outright could permanently lock a leaf out of its own best
    rescue chance if it hadn't differentiated yet. The soft version keeps
    every question selectable and only shifts the odds.)

    Deviates from the ticket's one-line signature by taking `leaf_profiles`
    and `age_group` explicitly: neither entropy nor age eligibility can be
    computed from `session`/`candidate_questions` alone. Excludes questions
    already in session.asked_question_ids and ones that don't match age_group
    (age_variant="both" is always eligible). Returns None only if nothing at
    all qualifies (the bank has genuinely run dry for this session).
    """
    beta = settings.AKINATOR_BETA if beta is None else beta
    temperature = settings.AKINATOR_QUESTION_TEMPERATURE if temperature is None else temperature
    rng = random.Random() if rng is None else rng
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

    entropies = [
        _expected_posterior_entropy(q, session.belief, leaf_profiles, beta) for q in candidates
    ]
    if session.step >= _RELEVANCE_ONSET_STEP:
        entropies = [
            e - _relevance_bonus(q, session.belief, _RELEVANCE_TOP_N)
            for q, e in zip(candidates, entropies)
        ]
    return _sample_by_entropy(candidates, entropies, temperature, rng)


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
    """Always take the top `k` leaves (belief-descending) as the cluster —
    never fewer, so a cluster reveal always offers exactly `min(k,
    len(sorted_leaves))` professions to choose from, instead of stopping
    early the moment cumulative probability crosses `threshold`. `threshold`
    still gates *whether* this set is confident enough to reveal at all (see
    check_stop), just not how many leaves are in it."""
    cluster = sorted_leaves[:k]
    cumulative = sum(prob for _, prob in cluster)
    return [leaf for leaf, _ in cluster], cumulative


ALL_AXIS_FAMILIES: frozenset[str] = frozenset(family.value for family in AxisFamily)


def check_stop(
    belief: dict[str, float],
    step: int,
    age_group: str,
    *,
    t: float | None = None,
    m: float | None = None,
    cluster_k: int | None = None,
    cluster_threshold: float | None = None,
    asked_families: set[str] | frozenset[str] | None = None,
) -> StopDecision:
    """Decide whether to stop and what to reveal, per profi_axes_phase1.md
    "Критерий остановки":
      - single leaf if top1 > T and top1 >= M * top2 (confident winner);
      - else a cluster of <= cluster_k leaves once their cumulative belief
        reaches cluster_threshold (close race, but a small group stands out);
      - else continue — unless the age-based question ceiling is reached, in
        which case a cluster is forced regardless of how flat belief still is
        (a valid outcome, never an error).

    `asked_families` (optional, backward-compatible default None disables
    this check) blocks a *confidence*-based reveal until all 5 axis families
    have been touched at least once — otherwise a leaf like "surgeon" could
    win purely on family A/B/C/D answers, without a single question ever
    probing family E (Math/Living/PhysSt/Acad — "do you actually like
    biology/math", "are you willing to study for years"). The ceiling
    override still fires regardless of coverage: a valid fallback outcome
    beats stalling forever if the active question bank can't cover every
    family for this session.
    """
    t = settings.AKINATOR_STOP_T if t is None else t
    m = settings.AKINATOR_STOP_M if m is None else m
    cluster_k = settings.AKINATOR_STOP_CLUSTER_K if cluster_k is None else cluster_k
    cluster_threshold = (
        settings.AKINATOR_STOP_CLUSTER_THRESHOLD if cluster_threshold is None else cluster_threshold
    )
    families_covered = asked_families is None or ALL_AXIS_FAMILIES.issubset(asked_families)

    sorted_leaves = sorted(belief.items(), key=lambda item: item[1], reverse=True)
    top1_leaf, top1_prob = sorted_leaves[0]
    top2_prob = sorted_leaves[1][1] if len(sorted_leaves) > 1 else 0.0

    if families_covered and top1_prob > t and top1_prob >= m * top2_prob:
        return StopDecision(status="reveal_single", leaves=[top1_leaf], reason="confidence")

    cluster, cluster_prob = _top_cluster(sorted_leaves, cluster_k, cluster_threshold)
    if families_covered and cluster_prob >= cluster_threshold:
        return StopDecision(status="reveal_cluster", leaves=cluster, reason="confidence")

    if step >= _age_ceiling(age_group):
        return StopDecision(status="reveal_cluster", leaves=cluster, reason="ceiling")

    return StopDecision(status="continue")
