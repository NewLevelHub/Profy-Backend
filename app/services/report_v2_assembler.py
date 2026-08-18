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
from app.services.mi_content import MI_ACTIVITIES, MI_LABELS
from app.services.mi_service import MI_ORDER
from app.services.riasec_content import NEUTRAL_CAREER_WHY, NEUTRAL_TRY_NOW, RIASEC_LABELS
from app.services.riasec_service import HOLLAND_ORDER, direction_letter_weight

# TZ_Profi.md §16.6: "разброс между максимальной и минимальной категорией
# меньше 25 пунктов" — a provisional default. §16.4 wants matrix/threshold
# tuning admin-configurable eventually; not built here, just not re-derived
# ad hoc at every call site either.
_FLAT_PROFILE_THRESHOLD = 25.0

# result-report-redesign-plan.md's recommended starting thresholds for the
# 0-100 normalized scale.
_LEVEL_HIGH_MIN = 70.0
_LEVEL_MEDIUM_MIN = 50.0

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
_FLAT_PROFILE_ARTIFACT_NOTE = (
    " Отдельно ты рассказал(а) о своих увлечениях в профиле — когда баллы "
    "по разным сферам близки друг к другу, как сейчас, эти увлечения могут "
    "точнее говорить о твоих склонностях, чем сам тест. Стоит присмотреться "
    "и к направлениям, связанным с ними, даже если их нет в списке ниже."
)


def is_flat_profile(differentiation: float) -> bool:
    return differentiation < _FLAT_PROFILE_THRESHOLD


def _level(value: float) -> Literal["low", "medium", "high"]:
    if value >= _LEVEL_HIGH_MIN:
        return "high"
    if value >= _LEVEL_MEDIUM_MIN:
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
    high = [i.sphere for i in items if i.level == "high"]
    if high:
        return f"Ярко выражено: {_join_ru(high)}. Остальные сферы проявляются тише — и это нормально."
    medium = [i.sphere for i in items if i.level == "medium"]
    if medium and len(medium) < len(items) / 2:
        return (
            f"Заметнее всего проявляется: {_join_ru(medium)} — без резких пиков, "
            f"интересы распределены довольно ровно."
        )
    return (
        "Пока сложно выделить одну явно ведущую сферу — интересы распределены "
        "довольно ровно, и это нормально: есть время присмотреться к разным направлениям."
    )


def build_interest_map(age_group: AgeGroup, profile_scores: dict[str, float]) -> list[StudentInterestMapItem]:
    """All 6 RIASEC spheres (middle/senior) or all 8 MI spheres (junior), in
    a fixed order — every category, not just the ones evidenced as a
    "strength" (that subset is what report_narrative's `interests` field
    covers instead, tier strong/steady; this is the numeric-level map)."""
    if age_group == AgeGroup.junior:
        order, labels = MI_ORDER, MI_LABELS
    else:
        order, labels = HOLLAND_ORDER, RIASEC_LABELS
    return [
        StudentInterestMapItem(code=key, sphere=labels[key], level=_level(profile_scores.get(key, 0.0)))
        for key in order
    ]


def build_personality_notes(is_junior: bool, personality_profile: dict[str, float]) -> list[StudentPersonalityNote]:
    """"Твой характер" — TZ_Profi.md's Big Five instrument is answered
    identically by all three age groups (only interests/motivation branch
    by age), so unlike interest_map this never varies by instrument, only
    by wording (junior gets bigfive_content._NOTES_JUNIOR's short, concrete
    phrasing instead of the adult table). Entirely deterministic, no LLM,
    no narrative pipeline involved — `personality_profile` is already a
    plain 5-domain float dict (report_service.py computes it once,
    unconditionally, for every age group), so this is a straight lookup,
    same shape as build_interest_map."""
    notes = bigfive_content.personality_notes_for_age(is_junior, personality_profile)
    return [
        StudentPersonalityNote(trait=trait, label=label, description=notes[trait])
        for trait, label in bigfive_content.PERSONALITY_LABELS.items()
    ]


def build_personality_note(personality_profile: dict[str, float]) -> str:
    """1-2 sentences of synthesis on top of the 5 static tiered cards
    `build_personality_notes` renders — the cards alone read as a plain
    lookup table with "no analysis" (reported live), same gap
    build_interest_map_note already closes for the interest map. Same
    minority guard as build_interest_map_note: naming traits only reads as
    a highlight if it's not most of them."""
    high = [
        label
        for trait, label in bigfive_content.PERSONALITY_LABELS.items()
        if bigfive_content.is_high_tier(personality_profile.get(trait, 0.0))
    ]
    if high and len(high) < len(bigfive_content.PERSONALITY_LABELS) / 2:
        return (
            f"Ярко выражено: {_join_ru(high)} — это то, что тебе, скорее всего, "
            f"даётся естественнее всего."
        )
    return (
        "Черты характера выражены сбалансированно, без одной резко доминирующей — "
        "и это нормально, у характера не обязательно должна быть одна главная черта."
    )


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
        activities.extend(MI_ACTIVITIES.get(key, [])[:2])
    if activities:
        return activities
    return [acts[0] for acts in MI_ACTIVITIES.values() if acts]


def _join_ru(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " и " + items[-1]


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
    vetted evidence the way citing an unconfirmed RIASEC letter would."""
    top = careers[:10]
    result: list[StudentCareer] = []
    seen_evidence: set[tuple[str, ...]] = set()
    for rank, career in enumerate(top, start=1):
        holland_code = career.get("holland_code", "")
        matched_strengths = _matched_strengths_for(holland_code, context)
        why = (
            f"Совпадает с тем, что у тебя выражено: {_join_ru(matched_strengths)}."
            if matched_strengths
            else NEUTRAL_CAREER_WHY
        )
        evidence_key = tuple(matched_strengths)
        skills_needed = list(career.get("skills_needed") or [])
        if evidence_key and evidence_key in seen_evidence and skills_needed:
            why += f" Именно здесь особенно пригодится: {skills_needed[0]}."
        seen_evidence.add(evidence_key)
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
            try_now=first_steps[0] if first_steps else NEUTRAL_TRY_NOW,
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
        common["summary"] = common["summary"] + _FLAT_PROFILE_ARTIFACT_NOTE

    return RiasecResultResponse(
        **common,
        interest_map=interest_map,
        careers=build_riasec_careers(context, careers),
    )
