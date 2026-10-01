"""Student-facing «Сильные стороны» (PRO-432): which strengths a report may
honestly show, decided deterministically before any LLM is involved.

Every card is a `StrengthCandidate` built from an already-scored instrument
and grounded in one of four ways (`basis`):
- task_result  — АСТУР task groups the student did best on;
- self_report  — ДДО «Хочу + Могу», the leading Belbin role(s), empathy /
  social confidence (Бойко + Кондаш), Elers' positive band;
- cross_signal — a RIASEC interest confirmed by a second instrument;
- interest     — a RIASEC or ДДО interest on its own, worded as something
  to try, never as a proven ability.

What never becomes a strength: the lie scale / validity flags, the
psychoemotional test, anxiety as a trait, Belbin's avoidance zone, Eysenck's
temperament, low bands, Elers' `too_high`, a protocol АСТУР itself marks as
not ok. Rules and cut-offs live in `app/data/student_strengths_rules.json`.

Selection: one fact (`evidence_ids`) backs at most one card and different
meaning domains are preferred. A completed RIASEC profile supplies the
remaining cautiously worded interest observations so the student sees exactly
`max_cards`; onboarding subjects and hobbies never become strength cards.
"""
import hashlib
import json
import logging
import uuid
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import StudentStrengthsRules, student_strengths_rules
from app.i18n import use_locale
from app.i18n.catalog import tr
from app.models.analysis_result import AnalysisResult, ReviewStatus
from app.models.artifact import Artifact
from app.models.assessment import Assessment
from app.models.profile import Profile
from app.schemas.astur import AsturResultSnapshot
from app.schemas.report_narrative import NarrativeCard
from app.schemas.student_strengths import OnboardingArtifact, StrengthCandidate, StrengthInputs
from app.services import (
    belbin_service,
    boyko_empathy_service,
    elers_service,
    eysenck_service,
    kondash_anxiety_service,
    professional_types_service,
    riasec_service,
)
from app.services.astur import runs as astur_runs

logger = logging.getLogger(__name__)

# ── АСТУР ────────────────────────────────────────────────────────────────────
# Task groups a card can speak about. Awareness (subject-term knowledge) is
# deliberately absent: it measures what was taught, not a way of thinking.
_ASTUR_GROUPS: dict[str, tuple[str, ...]] = {
    # Keep the skills as narrow as the task that demonstrated them. Combining
    # two unlike subtests used to hide a clear local result when the paired
    # subtest was weak (for example classification 8/12 + generalization 0/38).
    "verbal_connections": ("analogies",),
    "logical_reasoning": ("logical_schemas",),
    "categorization": ("classification",),
    "generalization": ("generalization",),
    "numeric": ("numeric_series",),
    "spatial": ("geometric_figures",),
}
_ASTUR_INSTRUCTIONS_GROUP = "instructions"

# ── Бойко ────────────────────────────────────────────────────────────────────
# Channels with their own wording; the other two fold into the general card.
_EMPATHY_NAMED_CHANNELS: tuple[str, ...] = ("rational", "emotional", "identification", "penetration")

# ── Cross-test signals ───────────────────────────────────────────────────────
# RIASEC letter + the second-source facts that confirm it, in preference
# order. The first available one is cited, and both facts are then used up.
_CROSS_SIGNALS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("people", "S", "social", ("empathy", "belbin:team_worker")),
    ("lead", "E", "team", ("social_confidence", "belbin:coordinator", "belbin:shaper")),
    ("order", "C", "activity", ("belbin:finisher", "belbin:implementer")),
    (
        "research", "I", "cognitive",
        (
            "ddo:sign", "ddo:technical", "astur:verbal_connections", "astur:logical_reasoning",
            "astur:categorization", "astur:generalization", "astur:numeric",
        ),
    ),
    ("creative", "A", "activity", ("ddo:artistic",)),
    ("practical", "R", "activity", ("ddo:technical", "ddo:practical")),
)

# Sources that are self-descriptions from the test battery — dropped when the
# Eysenck lie scale says the answers lean towards the socially desirable.
_SELF_REPORT_TEST_SOURCES = frozenset(
    {"professional_types", "belbin", "empathy", "social_confidence", "elers", "cross"}
)

# DDO and RIASEC describe some of the same activity areas. Once a selected
# DDO card already tells the student about that area, do not spend another
# one of the five slots repeating it under a different test's terminology.
_DDO_RIASEC_OVERLAP: dict[str, tuple[str, ...]] = {
    "practical": ("R",),
    "technical": ("R",),
    "social": ("S",),
    "sign": ("C",),
    "artistic": ("A",),
}

# ── inputs ───────────────────────────────────────────────────────────────────


def build_inputs(
    *,
    riasec_confirmed: list[str],
    riasec_ranked: list[str],
    ddo_interest: dict[str, int] | None,
    ddo_abilities: dict[str, int] | None,
    belbin_run: object | None,
    astur_run: object | None,
    empathy_data: dict | None,
    confidence_data: dict | None,
    elers_data: dict | None,
    eysenck_data: dict | None,
    subjects_liked: list[str],
    subjects_easy: list[str],
    artifacts: list[Artifact],
) -> StrengthInputs:
    """Shapes results the caller already scored (report_service computes
    them for the specialist sections anyway) into the selection's input."""
    astur = None
    if astur_run is not None and getattr(astur_run, "result_snapshot", None):
        try:
            astur = AsturResultSnapshot.model_validate(astur_run.result_snapshot)
        except Exception:  # noqa: BLE001 — a malformed snapshot just yields no АСТУР card
            logger.exception("АСТУР snapshot of run %s is unreadable — skipped for strengths", astur_run.id)
    return StrengthInputs(
        riasec_confirmed=list(riasec_confirmed),
        riasec_ranked=list(riasec_ranked),
        ddo_interest=ddo_interest,
        ddo_abilities=ddo_abilities,
        belbin_role_totals=dict(belbin_run.role_totals) if belbin_run is not None else None,
        astur=astur,
        empathy_channels=(empathy_data or {}).get("empathy_channels"),
        empathy_level=(empathy_data or {}).get("empathy_level"),
        confidence_level=(confidence_data or {}).get("confidence_level"),
        elers_level=(elers_data or {}).get("level"),
        lie_flagged=bool((eysenck_data or {}).get("protocol_flagged")),
        subjects_liked=list(subjects_liked),
        subjects_easy=list(subjects_easy),
        artifacts=[OnboardingArtifact(id=str(a.id), value=a.value) for a in artifacts],
    )


async def latest_battery_runs(assessment_id: uuid.UUID, db: AsyncSession) -> tuple[object | None, object | None]:
    """(latest Belbin run, latest completed АСТУР run) — the runs a report's
    strengths are built from."""
    belbin_run = await belbin_service.get_latest_run(assessment_id, db)
    astur_run = await astur_runs.latest_completed_run(db, assessment_id)
    return belbin_run, astur_run


async def collect_inputs(assessment_id: uuid.UUID, db: AsyncSession) -> StrengthInputs:
    """Re-reads every instrument for an assessment — the retake / refresh
    path, where no report generation has scored anything in memory."""
    profile = (
        await db.execute(
            select(Profile).join(Assessment, Assessment.profile_id == Profile.id).where(Assessment.id == assessment_id)
        )
    ).scalar_one_or_none()
    artifacts = (
        list((await db.execute(select(Artifact).where(Artifact.profile_id == profile.id))).scalars().all())
        if profile is not None
        else []
    )

    raw = await riasec_service.raw_scores(assessment_id, db)
    counts = await riasec_service.question_counts(db)
    normalized = riasec_service.normalize(raw, counts)
    aversion = await riasec_service.aversion(assessment_id, db)

    belbin_run, astur_run = await latest_battery_runs(assessment_id, db)
    kondash_raw = await kondash_anxiety_service.interpersonal_raw_score(assessment_id, db)
    return build_inputs(
        riasec_confirmed=riasec_service.confirmed_interests(normalized, aversion, counts),
        riasec_ranked=riasec_service.ranked_interests(normalized),
        ddo_interest=await professional_types_service.interest_raw_scores(assessment_id, db),
        ddo_abilities=await professional_types_service.abilities_raw_scores(assessment_id, db),
        belbin_run=belbin_run,
        astur_run=astur_run,
        empathy_data=boyko_empathy_service.build_section_data(
            await boyko_empathy_service.raw_scores(assessment_id, db)
        ),
        confidence_data=kondash_anxiety_service.build_confidence_data(
            kondash_raw, age=profile.age if profile is not None else 16
        ),
        elers_data=elers_service.build_section_data(await elers_service.raw_score(assessment_id, db)),
        eysenck_data=eysenck_service.build_section_data(await eysenck_service.raw_scores(assessment_id, db)),
        subjects_liked=list(profile.subjects_liked or []) if profile is not None else [],
        subjects_easy=list(profile.subjects_easy or []) if profile is not None else [],
        artifacts=artifacts,
    )


def fingerprint(candidates: list[StrengthCandidate]) -> str:
    """Identity of a report's strengths: which cards, grounded how, on which
    facts — locale-free. A retake that leaves them the same (e.g. Belbin
    resubmitted with the same leading role) doesn't make the report stale;
    any change to what the cards would say does."""
    payload = {
        "rules_version": student_strengths_rules.version,
        "candidates": [[c.source_id, c.basis, c.evidence_ids] for c in candidates],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


def rules_version_is_outdated(meta: dict | None) -> bool:
    """Whether stored cards predate the currently configured methodology."""
    return (meta or {}).get("strengths_rules_version") != student_strengths_rules.version


def rules_version_is_outdated_clause():
    """SQL equivalent of :func:`rules_version_is_outdated` for queues."""
    stored = AnalysisResult.meta.op("->>")("strengths_rules_version")
    return func.coalesce(stored, "") != str(student_strengths_rules.version)


def strengths_are_stale(meta: dict | None) -> bool:
    return bool((meta or {}).get("strengths_stale")) or rules_version_is_outdated(meta)


# ── candidates ───────────────────────────────────────────────────────────────


def _join(t: dict, items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + t["list_conjunction"] + items[-1]


def _card(t: dict, content_key: str, **params: str) -> dict[str, str]:
    content = t["cards"][content_key]
    return {
        "title": content["title"].format(**params),
        "description": content["description"].format(**params),
    }


def _astur_candidates(snapshot: AsturResultSnapshot | None, t: dict, rules: StudentStrengthsRules) -> list[StrengthCandidate]:
    if snapshot is None or not snapshot.protocol_quality.ok:
        return []
    by_key = {s.key: s for s in snapshot.subtests if s.in_overall and s.max_score > 0}
    scored: list[tuple[str, float]] = []
    for group, keys in _ASTUR_GROUPS.items():
        if not all(key in by_key for key in keys):
            continue
        earned = sum(by_key[key].score for key in keys)
        maximum = sum(by_key[key].max_score for key in keys)
        percent = earned / maximum * 100
        if percent >= rules.astur_min_percent:
            scored.append((group, percent))

    quick = snapshot.quick_instructions
    halves_total = (quick.first_half_total + quick.second_half_total) if quick else 0
    if quick is not None and quick.status == "ok" and halves_total:
        percent = (quick.first_half_correct + quick.second_half_correct) / halves_total * 100
        if percent >= rules.astur_quick_min_percent:
            scored.append((_ASTUR_INSTRUCTIONS_GROUP, percent))

    group_order = [*_ASTUR_GROUPS, _ASTUR_INSTRUCTIONS_GROUP]
    best = sorted(scored, key=lambda item: (-item[1], group_order.index(item[0])))[: rules.astur_max_cards]
    flags = ["astur_repeat_exposure"] if snapshot.history.repeat_exposure else []
    candidates: list[StrengthCandidate] = []
    for group, _ in best:
        content = _card(t, f"astur.{group}")
        if flags:
            content["description"] += t["astur_repeat_note"]
        candidates.append(StrengthCandidate(
            source_id=f"strength:astur:{group}",
            source_type="astur",
            domain="cognitive",
            basis="task_result",
            content_key=f"astur.{group}",
            evidence_ids=[f"astur:{group}"],
            quality_flags=flags,
            priority=1,
            **content,
        ))
    return candidates


def _ddo_matches(inputs: StrengthInputs, rules: StudentStrengthsRules) -> tuple[list[str], list[str]]:
    """(«Хочу + Могу» scales strongest first, «Могу > Хочу» scales)."""
    if not inputs.ddo_interest or not inputs.ddo_abilities:
        return [], []
    order = professional_types_service.SCALE_ORDER
    maxima = professional_types_service.INTEREST_MAX_BY_SCALE
    share = {s: inputs.ddo_interest.get(s, 0) / maxima[s] for s in order if maxima.get(s)}
    ability = {s: inputs.ddo_abilities.get(s, 0) for s in order}
    matched = [s for s in share if share[s] >= rules.ddo_interest_min_share and ability[s] >= rules.ddo_ability_min]
    matched.sort(key=lambda s: (-(share[s] + ability[s] / professional_types_service.ABILITY_MAX), order.index(s)))
    ability_only = [
        s for s in share
        if s not in matched
        and ability[s] >= rules.ddo_ability_only_min
        and share[s] < rules.ddo_ability_only_interest_max_share
    ]
    return matched, ability_only


def _ddo_candidates(inputs: StrengthInputs, t: dict, rules: StudentStrengthsRules) -> list[StrengthCandidate]:
    matched, ability_only = _ddo_matches(inputs, rules)
    spheres = t["ddo_spheres"]
    values = t["ddo_value"]
    candidates: list[StrengthCandidate] = []
    if len(matched) >= 2:
        # Two leading spheres: one hybrid card, not a winner by key order.
        first, second = sorted(matched[:2], key=professional_types_service.SCALE_ORDER.index)
        candidates.append(StrengthCandidate(
            source_id=f"strength:ddo_hybrid:{first}+{second}",
            source_type="professional_types",
            domain="activity",
            basis="self_report",
            content_key="ddo.hybrid",
            evidence_ids=[f"ddo:{first}", f"ddo:{second}"],
            priority=2,
            **_card(t, "ddo.hybrid", first=spheres[first], second=spheres[second]),
        ))
    # Single-sphere cards stay available for when a cross-test card has used
    # up one of the hybrid's spheres.
    for scale in matched:
        candidates.append(StrengthCandidate(
            source_id=f"strength:ddo:{scale}",
            source_type="professional_types",
            domain="activity",
            basis="self_report",
            content_key="ddo.match",
            evidence_ids=[f"ddo:{scale}"],
            priority=2,
            **_card(t, "ddo.match", sphere=spheres[scale], value=values[scale]),
        ))
    if ability_only:
        scales = ability_only[:2]
        candidates.append(StrengthCandidate(
            source_id="strength:ddo_ability:" + "+".join(scales),
            source_type="professional_types",
            domain="activity",
            basis="self_report",
            content_key="ddo.ability_only",
            evidence_ids=[f"ddo_ability:{s}" for s in scales],
            priority=4,
            **_card(
                t,
                "ddo.ability_only",
                spheres=t["list_conjunction"].join(spheres[s] for s in scales),
                value=t["list_conjunction"].join(values[s] for s in scales),
            ),
        ))
    matched_set = set(matched)
    if inputs.ddo_interest:
        interest_only = sorted(
            (
                scale for scale in professional_types_service.SCALE_ORDER
                if scale not in matched_set
                and inputs.ddo_interest.get(scale, 0) / professional_types_service.INTEREST_MAX_BY_SCALE[scale]
                >= rules.ddo_interest_min_share
            ),
            key=lambda scale: (
                -inputs.ddo_interest.get(scale, 0) / professional_types_service.INTEREST_MAX_BY_SCALE[scale],
                professional_types_service.SCALE_ORDER.index(scale),
            ),
        )
        if interest_only:
            scale = interest_only[0]
            candidates.append(StrengthCandidate(
                source_id=f"strength:ddo_interest:{scale}",
                source_type="professional_types",
                domain="interest",
                basis="interest",
                content_key="ddo.interest",
                evidence_ids=[f"ddo_interest:{scale}"],
                priority=6,
                **_card(t, "ddo.interest", sphere=spheres[scale], value=values[scale]),
            ))
    return candidates


def belbin_roles(
    role_totals: dict[str, int] | None, rules: StudentStrengthsRules = student_strengths_rules
) -> tuple[list[str], list[str]]:
    """(leading roles for a card, roles strong enough to confirm a RIASEC
    interest). Leading = within `belbin_tie_margin` of the top score; three
    or more of them is no clear signal. Never an avoidance-zone role."""
    if not role_totals:
        return [], []
    interpretation = belbin_service.interpret_role_totals(role_totals)
    avoidance = set(interpretation.avoidance_roles)

    def eligible(role: str) -> bool:
        return role not in avoidance and role_totals[role] >= rules.belbin_min_score

    top_score = role_totals[interpretation.dominant_role]
    leading = [
        r for r in interpretation.ranked_roles
        if top_score - role_totals[r] <= rules.belbin_tie_margin and eligible(r)
    ]
    if len(leading) > 2:
        leading = []
    strong = [r for r in interpretation.ranked_roles[:3] if eligible(r)]
    strong += [r for r in leading if r not in strong]
    return leading, strong


def _belbin_candidates(inputs: StrengthInputs, t: dict, rules: StudentStrengthsRules) -> list[StrengthCandidate]:
    leading, _ = belbin_roles(inputs.belbin_role_totals, rules)
    contributions = t["belbin_contributions"]
    candidates: list[StrengthCandidate] = []
    if len(leading) == 2:
        first, second = leading
        candidates.append(StrengthCandidate(
            source_id=f"strength:belbin:{first}+{second}",
            source_type="belbin",
            domain="team",
            basis="self_report",
            content_key="belbin.pair",
            evidence_ids=[f"belbin:{first}", f"belbin:{second}"],
            priority=3,
            **_card(t, "belbin.pair", first=contributions[first], second=contributions[second]),
        ))
    for role in leading:
        candidates.append(StrengthCandidate(
            source_id=f"strength:belbin:{role}",
            source_type="belbin",
            domain="team",
            basis="self_report",
            content_key="belbin.single",
            evidence_ids=[f"belbin:{role}"],
            priority=3,
            **_card(t, "belbin.single", contribution=contributions[role]),
        ))
    return candidates


def _empathy_candidates(inputs: StrengthInputs, t: dict, rules: StudentStrengthsRules) -> list[StrengthCandidate]:
    candidates: list[StrengthCandidate] = []
    channels = inputs.empathy_channels
    if channels and inputs.empathy_level in rules.empathy_levels:
        top_score = max(channels.values())
        top = [c for c in boyko_empathy_service.CHANNELS if channels.get(c, 0) == top_score]
        key = (
            top[0]
            if len(top) == 1 and top[0] in _EMPATHY_NAMED_CHANNELS and top_score >= rules.empathy_channel_min
            else "general"
        )
        card = _card(t, f"empathy.{key}")
        if inputs.empathy_level == "very_high":
            # Very high empathy stays a resource only with the boundary caveat.
            card["description"] += t["empathy_boundary_note"]
        candidates.append(StrengthCandidate(
            source_id=f"strength:empathy:{key}",
            source_type="empathy",
            domain="social",
            basis="self_report",
            content_key=f"empathy.{key}",
            evidence_ids=["empathy"],
            priority=4,
            **card,
        ))
    if inputs.confidence_level == "high":
        candidates.append(StrengthCandidate(
            source_id="strength:social_confidence",
            source_type="social_confidence",
            domain="social",
            basis="self_report",
            content_key="social_confidence",
            evidence_ids=["social_confidence"],
            priority=4,
            **_card(t, "social_confidence"),
        ))
    return candidates


def _elers_candidates(inputs: StrengthInputs, t: dict) -> list[StrengthCandidate]:
    # Only the methodologically positive band — `too_high` is a burnout /
    # perfectionism risk, never a strength.
    if inputs.elers_level != "moderately_high":
        return []
    return [StrengthCandidate(
        source_id="strength:elers",
        source_type="elers",
        domain="self_regulation",
        basis="self_report",
        content_key="elers",
        evidence_ids=["elers"],
        priority=5,
        **_card(t, "elers"),
    )]


def _cross_candidates(
    inputs: StrengthInputs, others: list[StrengthCandidate], t: dict, rules: StudentStrengthsRules
) -> list[StrengthCandidate]:
    _, strong_roles = belbin_roles(inputs.belbin_role_totals, rules)
    available = {e for c in others for e in c.evidence_ids} | {f"belbin:{r}" for r in strong_roles}
    letters = set(inputs.riasec_confirmed)
    candidates: list[StrengthCandidate] = []
    for name, letter, domain, confirmations in _CROSS_SIGNALS:
        if letter not in letters:
            continue
        second = next((e for e in confirmations if e in available), None)
        if second is None:
            continue
        candidates.append(StrengthCandidate(
            source_id=f"strength:cross:{name}",
            source_type="cross",
            domain=domain,
            basis="cross_signal",
            content_key=f"cross.{name}",
            evidence_ids=[f"riasec:{letter}", second],
            priority=1,
            **_card(t, f"cross.{name}"),
        ))
    return candidates


def _interest_candidates(
    inputs: StrengthInputs, used: set[str], t: dict, rules: StudentStrengthsRules
) -> list[StrengthCandidate]:
    """Built last from relative RIASEC preferences no stronger card used.

    One letter per card makes every observation understandable and lets the
    section reach five without merging several unrelated interests into one
    vague sentence. Wording stays exploratory: rank is not ability.
    """
    result: list[StrengthCandidate] = []
    # `riasec_confirmed` is a compatibility fallback for direct/unit callers;
    # production report paths always provide the complete relative ranking.
    for letter in inputs.riasec_ranked or inputs.riasec_confirmed:
        evidence_id = f"riasec:{letter}"
        if evidence_id in used:
            continue
        result.append(StrengthCandidate(
            source_id=f"strength:interest:{letter}",
            source_type="riasec",
            domain="interest",
            basis="interest",
            content_key=f"interest.{letter}",
            evidence_ids=[evidence_id],
            priority=7,
            **_card(t, f"interest.{letter}"),
        ))
    return result


def _select(candidates: list[StrengthCandidate], rules: StudentStrengthsRules) -> list[StrengthCandidate]:
    """Greedy by priority. First pass: the best card of each domain; second:
    fill up to `max_cards` with at most `max_per_domain` per domain. A card
    whose facts are already used by a chosen card is skipped."""
    ordered = sorted(enumerate(candidates), key=lambda pair: (pair[1].priority, pair[0]))
    chosen: list[int] = []
    used: set[str] = set()
    per_domain: Counter[str] = Counter()
    for cap in (1, rules.max_per_domain):
        for index, candidate in ordered:
            if len(chosen) >= rules.max_cards:
                break
            if index in chosen or used & set(candidate.evidence_ids) or per_domain[candidate.domain] >= cap:
                continue
            chosen.append(index)
            used |= set(candidate.evidence_ids)
            per_domain[candidate.domain] += 1
    return [candidates[i] for i in sorted(chosen, key=lambda i: (candidates[i].priority, i))]


def select_strengths(
    inputs: StrengthInputs, *, rules: StudentStrengthsRules = student_strengths_rules
) -> list[StrengthCandidate]:
    """The vetted strength cards for one report, in display order. Renders
    in the current request locale (callers wrap it in `use_locale`)."""
    t = tr("student_strengths")
    others = (
        _astur_candidates(inputs.astur, t, rules)
        + _ddo_candidates(inputs, t, rules)
        + _belbin_candidates(inputs, t, rules)
        + _empathy_candidates(inputs, t, rules)
        + _elers_candidates(inputs, t)
    )
    candidates = _cross_candidates(inputs, others, t, rules) + others
    if inputs.lie_flagged and rules.suppress_self_report_on_lie_flag:
        candidates = [
            c for c in candidates
            if c.source_type not in _SELF_REPORT_TEST_SOURCES or c.basis == "interest"
        ]

    selected = _select(candidates, rules)
    if len(selected) < rules.max_cards:
        used = {e for c in selected for e in c.evidence_ids}
        for evidence_id in tuple(used):
            prefix, separator, scale = evidence_id.partition(":")
            if separator and prefix in {"ddo", "ddo_interest"}:
                used.update(f"riasec:{letter}" for letter in _DDO_RIASEC_OVERLAP.get(scale, ()))
        for interest in _interest_candidates(inputs, used, t, rules):
            selected.append(interest)
            if len(selected) >= rules.max_cards:
                break
    return selected


# ── storage ──────────────────────────────────────────────────────────────────


def stored_cards(cards: list[NarrativeCard], candidates: list[StrengthCandidate]) -> list[dict]:
    """Persist titles plus server-authored, evidence-grounded explanations.

    The model may make a title friendlier, but the visible ``Why?`` text is
    always the candidate description selected by the methodology.
    """
    by_id = {c.source_id: c for c in candidates}
    result: list[dict] = []
    for card in cards:
        candidate = next((by_id[e] for e in card.evidence_ids if e in by_id), None)
        stored: dict = {
            "title": card.title,
            "description": candidate.description if candidate is not None else card.description,
        }
        if candidate is not None:
            stored["basis"] = candidate.basis
        result.append(stored)
    return result


def candidate_cards(candidates: list[StrengthCandidate]) -> list[dict]:
    """The deterministic wording of every candidate, already in stored shape."""
    return stored_cards(
        [NarrativeCard(title=c.title, description=c.description, evidence_ids=[c.source_id]) for c in candidates],
        candidates,
    )


# ── retakes ──────────────────────────────────────────────────────────────────


async def _report_rows(assessment_id: uuid.UUID, db: AsyncSession) -> list[AnalysisResult]:
    return list(
        (await db.execute(select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)))
        .scalars()
        .all()
    )


async def flag_report_if_strengths_changed(assessment_id: uuid.UUID, db: AsyncSession) -> bool:
    """Called after a Belbin attempt finishes. If a report already
    exists and was built from other results, its strength cards are now
    stale: the report goes back to review (never silently rewritten — the
    psychologist decides whether to rebuild the cards), and the psychologist
    is notified. Never raises into the submit that triggered it."""
    try:
        rows = await _report_rows(assessment_id, db)
        if not rows:
            return False
        current = fingerprint(select_strengths(await collect_inputs(assessment_id, db)))
        if all((row.meta or {}).get("strengths_fingerprint") == current for row in rows):
            return False
        was_published = any(row.review_status == ReviewStatus.published for row in rows)
        for row in rows:
            row.meta = {**(row.meta or {}), "strengths_stale": True}
            row.review_status = ReviewStatus.pending_review
        student = (
            await db.execute(
                select(Profile.user_id, Profile.name)
                .join(Assessment, Assessment.profile_id == Profile.id)
                .where(Assessment.id == assessment_id)
            )
        ).one_or_none()
        await db.commit()
    except Exception:  # noqa: BLE001 — the student's submit must not fail over this
        logger.exception("strengths staleness check failed for assessment=%s", assessment_id)
        await db.rollback()
        return False

    from app.services import assessment_shared, psychologist_service

    await assessment_shared.safe_redis_delete(
        assessment_shared.get_redis(), *assessment_shared.report_cache_keys(assessment_id)
    )
    if student is not None:
        await psychologist_service.notify_review_pending(
            db, student_id=student.user_id, student_name=student.name, assessment_id=assessment_id
        )
    logger.info(
        "report strengths stale for assessment=%s (was_published=%s) — back to review", assessment_id, was_published
    )
    return True


async def rebuild_cards(analysis: AnalysisResult, db: AsyncSession) -> tuple[list[dict], str]:
    """Fresh deterministic cards for a report row, in that row's language,
    and the fingerprint they were built from. Used by the psychologist's
    explicit «Пересобрать» action — no LLM, so the result is predictable."""
    inputs = await collect_inputs(analysis.assessment_id, db)
    with use_locale(analysis.locale):
        candidates = select_strengths(inputs)
    return candidate_cards(candidates), fingerprint(candidates)


def mark_fresh(meta: dict | None, strengths_fingerprint: str) -> dict:
    """Meta of a row whose strength cards match `strengths_fingerprint`."""
    fresh = {k: v for k, v in (meta or {}).items() if k != "strengths_stale"}
    fresh["strengths_fingerprint"] = strengths_fingerprint
    fresh["strengths_rules_version"] = student_strengths_rules.version
    return fresh
