"""Assembles the final student-facing /result v2 response
(app/schemas/result_v2.py, ResultResponseV2) from two independent pieces:

1. app.services.report_narrative_service.generate_report_narrative() —
   summary, strength_cards, thinking_style_notes: LLM-personalized when
   available, otherwise app.services.report_narrative_fallback's
   deterministic template, always passed through
   app.services.report_narrative_validator first either way. This module
   does not duplicate any of that text-generation/validation logic.
2. This module's own interest_map / careers / is_flat_profile — data the
   narrative pipeline deliberately never touches. report_narrative_fallback
   docstring: career_narrative "ничего не знает о конкретных
   направлениях/профессиях"; those come from the real `directions` table
   (riasec_service.matched_careers), a fact source, not narrative text
   (TZ_Profi.md §17.3 "правило факта" — facts come from the DB, not LLM/
   evidence prose).

Deterministic and DB-free itself: takes already-computed scoring output and
an already-resolved ReportNarrativeOutput, so the same input always
produces the same ResultResponseV2.
"""
import uuid
from datetime import datetime
from typing import Literal

from app.i18n.catalog import tr
from app.models.profile import AgeGroup
from app.schemas.report_narrative import ReportNarrativeOutput
from app.schemas.report_narrative_context import ReportNarrativeContext
from app.schemas.result_v2 import (
    MiResultResponse,
    ResultResponseV2,
    RiasecResultResponse,
    StudentCareer,
    StudentInterestMapItem,
    StudentPersonalityNote,
    StudentStrengthCard,
    StudentThinkingStyleNote,
)
from app.services import bigfive_content
from app.services.mi_content import mi_activities, mi_labels
from app.services.mi_service import MI_ORDER
from app.services.riasec_content import neutral_career_why_variants, neutral_try_now, riasec_labels
from app.services.riasec_service import HOLLAND_ORDER, direction_letter_weight
from app.services.scoring_levels import LEVEL_HIGH_MIN, LEVEL_MEDIUM_MIN

# TZ_Profi.md §16.6: "разброс между максимальной и минимальной категорией
# меньше 25 пунктов" — a provisional default. §16.4 wants matrix/threshold
# tuning admin-configurable eventually; not built here, just not re-derived
# ad hoc at every call site either.
_FLAT_PROFILE_THRESHOLD = 25.0

_GOOD_TIER_MAX_RANK = 3

# Career matching (career_match_score, riasec_service.py) runs purely on the
# RIASEC top-3 code — it has no way to know about subjects/artifacts, and a
# flat profile means that top-3 is itself close to noise (the difference
# between rank 3 and rank 4 might be a single point). Found live: a student
# with clear self-reported programming/robotics interest, but a flat RIASEC
# profile (differentiation 11.5), got Архивариус/Аудитор/Бухгалтер — three
# clerical directions with zero connection to what they'd actually told the
# app about themselves. Redesigning career_match_score to weigh non-RIASEC
# evidence is a real methodology change (result-quality-fixes.md §3, variant
# C) — not done here. The mitigation is the honest disclaimer below, not a
# shortened/uniform-tier career list (product decision, 2026-08-17): the
# ranking itself is still real RIASEC-derived signal even when it's a close
# call, so a flat profile shows the same ranked top-10 as everyone else.
# The flat-profile artifact addendum text is catalog result_v2
# ["flat_profile_artifact_note"] (KZ-403).


def is_flat_profile(differentiation: float) -> bool:
    return differentiation < _FLAT_PROFILE_THRESHOLD


def _level(value: float) -> Literal["low", "medium", "high"]:
    if value >= LEVEL_HIGH_MIN:
        return "high"
    if value >= LEVEL_MEDIUM_MIN:
        return "medium"
    return "low"


def build_interest_map_note(items: list[StudentInterestMapItem]) -> str:
    """1-2 sentences summarizing the numeric map itself — deterministic,
    straight from the already-computed levels, nothing to personalize
    beyond that (no LLM involved, unlike summary/final_analysis).

    The "medium" branch only fires when medium-tier spheres are a genuine
    minority (< half of all spheres) — naming a subset only reads as a
    highlight if it actually leaves most spheres out. Found live: a mostly-
    flat profile with 5 of 6 RIASEC spheres landing "medium" produced "Заметнее
    всего проявляется: [5 of 6 categories] — без резких пиков" — self-
    contradictory (calling out "most notable" while also saying nothing
    stands out) and useless as a highlight. That case now falls through to
    the honest flat-profile message instead."""
    t = tr("result_v2")
    high = [i.sphere for i in items if i.level == "high"]
    if high:
        return t["interest_map_note_high"].format(spheres=_join(high))
    medium = [i.sphere for i in items if i.level == "medium"]
    if medium and len(medium) < len(items) / 2:
        return t["interest_map_note_medium"].format(spheres=_join(medium))
    return t["interest_map_note_flat"]


def build_interest_map(age_group: AgeGroup, profile_scores: dict[str, float]) -> list[StudentInterestMapItem]:
    """All 6 RIASEC spheres (middle/senior) or all 8 MI spheres (junior),
    ranked most-to-least pronounced by score — every category, not just the
    ones evidenced as a "strength" (that subset is what report_narrative's
    `interests` field covers instead, tier strong/steady; this is the
    numeric-level map). Same score-desc/canonical-index tie-break convention
    as riasec_service.py's strengths/weaknesses ranking, just unfiltered."""
    if age_group == AgeGroup.junior:
        order, labels = MI_ORDER, mi_labels()
    else:
        order, labels = HOLLAND_ORDER, riasec_labels()
    ranked = sorted(order, key=lambda key: (-profile_scores.get(key, 0.0), order.index(key)))
    return [
        StudentInterestMapItem(code=key, sphere=labels[key], level=_level(profile_scores.get(key, 0.0)))
        for key in ranked
    ]


def build_personality_notes(is_junior: bool, personality_profile: dict[str, float]) -> list[StudentPersonalityNote]:
    """"Твой характер" — the Big Five instrument is answered identically by
    all three age groups (only interests/motivation branch by age), so
    unlike interest_map this never varies by instrument, only by wording
    (junior gets bigfive_content._NOTES_JUNIOR's short, concrete phrasing
    instead of the adult table). Entirely deterministic, no LLM, no
    narrative pipeline involved — `personality_profile` is already a plain
    5-domain float dict (report_service.py computes it once, unconditionally,
    for every age group). Ranked most-to-least pronounced, same
    score-desc/canonical-index tie-break convention as
    build_interest_map/riasec_service.py's strengths ranking. `level` is the
    trait's band relative to the student's own five-trait average
    (bigfive_content.relative_bands), not an absolute cutoff."""
    notes = bigfive_content.personality_notes_for_age(is_junior, personality_profile)
    bands = bigfive_content.relative_bands(personality_profile)
    traits = list(bigfive_content.personality_labels().items())
    ranked = sorted(traits, key=lambda item: (-personality_profile.get(item[0], 0.0), traits.index(item)))
    return [
        StudentPersonalityNote(
            trait=trait,
            label=label,
            description=notes[trait],
            level=bands.get(trait, "medium"),
        )
        for trait, label in ranked
    ]


def build_personality_note(personality_profile: dict[str, float]) -> str:
    """1-2 sentences of synthesis on top of the 5 static tiered cards
    `build_personality_notes` renders — the cards alone read as a plain
    lookup table with "no analysis" (reported live), same gap
    build_interest_map_note already closes for the interest map.

    Names genuinely low traits too, but ONLY the ones from
    `bigfive_content.GROWTH_ELIGIBLE_TRAITS` (openness, conscientiousness,
    emotional_stability — the same 3 domains `strength_phrases()` already
    treats as "skill-like", per the product decision recorded there).
    Extraversion/agreeableness are deliberately excluded from this
    low-side callout even when they cross the low band: this report is for
    a student to understand themselves and recognize genuine strengths —
    being introverted or being direct isn't a flaw to "fix", it's
    temperament, and naming it next to "стоит подтянуть" would frame a
    normal personality style as a deficiency. High-side naming keeps all 5
    traits (a genuinely high trait is worth naming as something that comes
    naturally, regardless of domain) — only the low/growth side is scoped
    down.

    High and low are reported independently (a profile can have both,
    either, or neither) — each is skipped if it would name literally every
    eligible trait (that's the whole list, not a highlight).

    Bands are relative to the student's own five-trait average
    (bigfive_content.relative_bands) — an even profile comes back all
    "medium", which is itself the meaningful-outlier gate, so no separate
    spread check is needed here."""
    labels = bigfive_content.personality_labels()
    bands = bigfive_content.relative_bands(personality_profile)
    high = [
        label for trait, label in labels.items()
        if bands.get(trait) == "high"
    ]
    low = [
        label for trait, label in labels.items()
        if trait in bigfive_content.GROWTH_ELIGIBLE_TRAITS
        and bands.get(trait) == "low"
    ]
    t = tr("result_v2")
    sentences = []
    if high and len(high) < len(labels):
        sentences.append(t["personality_note_high"].format(traits=_join(high)))
    if low and len(low) < len(bigfive_content.GROWTH_ELIGIBLE_TRAITS):
        sentences.append(t["personality_note_low"].format(traits=_join(low)))
    if sentences:
        return " ".join(sentences)
    return t["personality_note_balanced"]


def build_exploration_activities(context: ReportNarrativeContext) -> list[str]:
    """Always non-empty — MI never fakes career matching (TZ_Profi.md
    §4.1), it offers activities instead. Built from the top MI categories in
    context; if none qualified as evidence at all (an extremely flat
    profile with nothing vetted as a "strength"), falls back to one
    activity per category so the student still gets something safe to try
    rather than an empty list."""
    mi_items = [e for e in context.evidence if e.source_type == "mi_category"]
    activities: list[str] = []
    for item in mi_items:
        key = item.source_id.split(":", 1)[1]
        activities.extend(mi_activities().get(key, [])[:2])
    if activities:
        return activities
    return [acts[0] for acts in mi_activities().values() if acts]


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + tr("result_v2")["list_conjunction"] + items[-1]


def _matched_strengths_for(direction_code: str, context: ReportNarrativeContext) -> list[str]:
    """Ordered by how central each matched letter is to THIS direction's own
    code (primary letter first), not by the user's own top-3 rank — two
    directions sharing the same 3 letters in a different order (e.g. "ESC"
    vs "SEC") then read as differently-emphasized `why` text instead of a
    byte-identical sentence (riasec_service.direction_letter_weight)."""
    matches = [
        e for e in context.evidence
        if e.source_type == "riasec_category" and e.source_id.split(":", 1)[1] in direction_code
    ]
    matches.sort(key=lambda e: -direction_letter_weight(e.source_id.split(":", 1)[1], direction_code))
    return [e.text for e in matches]


def _tier_for_rank(rank: int) -> Literal["strong", "good", "worth_trying"]:
    if rank == 1:
        return "strong"
    if rank <= _GOOD_TIER_MAX_RANK:
        return "good"
    return "worth_trying"


def build_riasec_careers(
    context: ReportNarrativeContext,
    careers: list[dict],
) -> list[StudentCareer]:
    """`careers` is the raw list report_service already builds
    (riasec_service.matched_careers + report_service._career_dict, or the
    same shape read back from AnalysisResult.careers) — already sorted by
    match_score, so this only ever slices/labels, never re-ranks or re-sorts.

    Same top-10, ranked strong/good/worth_trying by rank for every profile,
    flat or not (product decision, 2026-08-17 — see the module-level comment
    above `_GOOD_TIER_MAX_RANK`). `why` is always non-empty: the direction's
    own Holland-code overlap with vetted RIASEC evidence when there is one,
    otherwise the neutral product-approved fallback — never blank, never
    invented beyond what's in `context`.

    Two shown directions can still be equally well-supported by the exact
    same confirmed evidence — e.g. codes "CSI" and "CSR" differ only in a
    letter that isn't one of the student's top-3 (so, correctly, it's not
    part of `why` at all): both get the identical matched_strengths in the
    identical order. Rather than repeat the sentence, the second (and any
    later) such card gets one extra clause naming something specific to
    THAT direction — its own catalog `skills_needed[0]`, a fact about the
    job, not a claim about the student, so this never overclaims beyond
    vetted evidence the way citing an unconfirmed RIASEC letter would.

    A flat profile can push most/all of the 10 cards into the no-overlap
    fallback branch — cycling through NEUTRAL_CAREER_WHY_VARIANTS (rather
    than repeating one sentence) keeps those cards from reading as
    copy-pasted; once every variant has been used once, later cards also
    get the same skills_needed[0] clause as the matched-evidence dedup
    above, so a 6th+ fallback card still reads distinct from the 1st."""
    t = tr("result_v2")
    top = careers[:10]
    result: list[StudentCareer] = []
    seen_evidence: set[tuple[str, ...]] = set()
    fallback_uses = 0
    for rank, career in enumerate(top, start=1):
        holland_code = career.get("holland_code", "")
        matched_strengths = _matched_strengths_for(holland_code, context)
        skills_needed = list(career.get("skills_needed") or [])
        if matched_strengths:
            why = t["career_why_match"].format(strengths=_join(matched_strengths))
            evidence_key = tuple(matched_strengths)
            if evidence_key in seen_evidence and skills_needed:
                why += t["career_why_skill_matched"].format(skill=skills_needed[0])
            seen_evidence.add(evidence_key)
        else:
            _why_variants = neutral_career_why_variants()
            why = _why_variants[fallback_uses % len(_why_variants)]
            if fallback_uses >= len(_why_variants) and skills_needed:
                why += t["career_why_skill_neutral"].format(skill=skills_needed[0])
            fallback_uses += 1
        # Direction.first_steps may hold several catalog entries, but the
        # student only ever sees one, as `try_now` — a separate "3 first
        # steps" list read as pointless filler on top of it (product
        # decision, result-quality-fixes.md §4).
        first_steps = list(career.get("first_steps") or [])
        result.append(StudentCareer(
            slug=career.get("slug", ""),
            name=career.get("name", ""),
            rank=rank,
            tier=_tier_for_rank(rank),
            why=why,
            matched_strengths=matched_strengths,
            try_now=first_steps[0] if first_steps else neutral_try_now(),
            description=career.get("description") or None,
            skills_needed=skills_needed,
            subjects_to_develop=list(career.get("subjects_to_develop") or []),
        ))
    return result


def _map_cards(cards: list) -> list[StudentStrengthCard]:
    return [StudentStrengthCard(title=c.title, description=c.description) for c in cards]


def _map_thinking_notes(cards: list) -> list[StudentThinkingStyleNote]:
    return [StudentThinkingStyleNote(title=c.title, description=c.description) for c in cards]


def assemble_result_v2(
    *,
    assessment_id: uuid.UUID,
    age_group: AgeGroup,
    context: ReportNarrativeContext,
    narrative: ReportNarrativeOutput,
    profile_scores: dict[str, float],
    personality_profile: dict[str, float],
    differentiation: float,
    careers: list[dict],
    created_at: datetime,
) -> ResultResponseV2:
    """Always succeeds, never raises, never leaves a required field empty —
    this is what makes /result return 200 with a complete v2 form
    regardless of whether `narrative` came from the LLM or its own
    deterministic fallback (report_service decides that; this function
    doesn't care which)."""
    flat = is_flat_profile(differentiation)
    interest_map = build_interest_map(age_group, profile_scores)
    common = dict(
        assessment_id=assessment_id,
        summary=narrative.summary,
        strength_cards=_map_cards(narrative.strength_cards),
        interest_map_note=build_interest_map_note(interest_map),
        thinking_style_notes=_map_thinking_notes(narrative.thinking_style_notes),
        personality_notes=build_personality_notes(age_group == AgeGroup.junior, personality_profile),
        personality_note=build_personality_note(personality_profile),
        motivation_highlights=[e.text for e in context.evidence if e.source_type == "motivation"],
        is_flat_profile=flat,
        final_analysis=narrative.final_analysis,
        created_at=created_at,
    )

    if age_group == AgeGroup.junior:
        return MiResultResponse(
            **common,
            interest_map=interest_map,
            exploration_activities=build_exploration_activities(context),
        )

    if flat and any(e.source_type == "artifact" for e in context.evidence):
        common["summary"] = common["summary"] + tr("result_v2")["flat_profile_artifact_note"]

    return RiasecResultResponse(
        **common,
        interest_map=interest_map,
        careers=build_riasec_careers(context, careers),
    )
