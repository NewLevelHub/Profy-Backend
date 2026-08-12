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
    StudentStrengthCard,
    StudentThinkingStyleNote,
)
from app.services.mi_content import MI_ACTIVITIES, MI_LABELS
from app.services.mi_service import MI_ORDER
from app.services.riasec_content import NEUTRAL_CAREER_WHY, NEUTRAL_TRY_NOW, RIASEC_LABELS
from app.services.riasec_service import HOLLAND_ORDER

# TZ_Profi.md §16.6: "разброс между максимальной и минимальной категорией
# меньше 25 пунктов" — a provisional default. §16.4 wants matrix/threshold
# tuning admin-configurable eventually; not built here, just not re-derived
# ad hoc at every call site either.
_FLAT_PROFILE_THRESHOLD = 25.0

# result-report-redesign-plan.md's recommended starting thresholds for the
# 0-100 normalized scale.
_LEVEL_HIGH_MIN = 70.0
_LEVEL_MEDIUM_MIN = 50.0

_FLAT_PROFILE_CAREER_COUNT = 3
_GOOD_TIER_MAX_RANK = 3


def is_flat_profile(differentiation: float) -> bool:
    return differentiation < _FLAT_PROFILE_THRESHOLD


def _level(value: float) -> Literal["low", "medium", "high"]:
    if value >= _LEVEL_HIGH_MIN:
        return "high"
    if value >= _LEVEL_MEDIUM_MIN:
        return "medium"
    return "low"


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
    return [
        e.text for e in context.evidence
        if e.source_type == "riasec_category" and e.source_id.split(":", 1)[1] in direction_code
    ]


def _tier_for_rank(rank: int) -> Literal["strong", "good", "worth_trying"]:
    if rank == 1:
        return "strong"
    if rank <= _GOOD_TIER_MAX_RANK:
        return "good"
    return "worth_trying"


def build_riasec_careers(
    context: ReportNarrativeContext,
    careers: list[dict],
    flat: bool,
) -> list[StudentCareer]:
    """`careers` is the raw list report_service already builds
    (riasec_service.matched_careers + report_service._career_dict, or the
    same shape read back from AnalysisResult.careers) — already sorted by
    match_score, so this only ever slices/labels, never re-ranks or re-sorts.

    Flat profile: exactly 3, all `worth_trying` (TZ_Profi.md §16.6). `why`
    is always non-empty: the direction's own Holland-code overlap with
    vetted RIASEC evidence when there is one, otherwise the neutral
    product-approved fallback — never blank, never invented beyond what's
    in `context`."""
    top = careers[:_FLAT_PROFILE_CAREER_COUNT] if flat else careers[:5]
    result: list[StudentCareer] = []
    for rank, career in enumerate(top, start=1):
        holland_code = career.get("holland_code", "")
        matched_strengths = _matched_strengths_for(holland_code, context)
        why = (
            f"Совпадает с тем, что у тебя выражено: {_join_ru(matched_strengths)}."
            if matched_strengths
            else NEUTRAL_CAREER_WHY
        )
        first_steps = list(career.get("first_steps") or [])
        result.append(StudentCareer(
            slug=career.get("slug", ""),
            name=career.get("name", ""),
            rank=rank,
            tier="worth_trying" if flat else _tier_for_rank(rank),
            why=why,
            matched_strengths=matched_strengths,
            try_now=first_steps[0] if first_steps else NEUTRAL_TRY_NOW,
            description=career.get("description") or None,
            skills_needed=list(career.get("skills_needed") or []),
            subjects_to_develop=list(career.get("subjects_to_develop") or []),
            first_steps=first_steps,
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
    common = dict(
        assessment_id=assessment_id,
        summary=narrative.summary,
        strength_cards=_map_cards(narrative.strength_cards),
        thinking_style_notes=_map_thinking_notes(narrative.thinking_style_notes),
        motivation_highlights=[e.text for e in context.evidence if e.source_type == "motivation"],
        is_flat_profile=flat,
        created_at=created_at,
    )

    if age_group == AgeGroup.junior:
        return MiResultResponse(
            **common,
            interest_map=build_interest_map(age_group, profile_scores),
            exploration_activities=build_exploration_activities(context),
        )

    return RiasecResultResponse(
        **common,
        interest_map=build_interest_map(age_group, profile_scores),
        careers=build_riasec_careers(context, careers, flat),
    )
