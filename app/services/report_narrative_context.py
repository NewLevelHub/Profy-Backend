"""Builds the safe evidence catalog (ReportNarrativeContext) that report
narrative generation, its output validator, and the deterministic fallback
are all meant to share — see app/schemas/report_narrative_context.py for why
this exists instead of reusing StudentContext.

Pure function, no DB access: called from report_service.build_report with
values it has already computed in memory (scores aren't re-fetched from a
stored AnalysisResult, since this runs before that row exists), including the
vetted strength candidates (app/services/student_strengths_service.py). This is
also why it never touches a response table: the motivation triplets are
already collapsed into motivation_top/motivation_highlights before this
function runs.
"""
from app.schemas.report_narrative_context import EvidenceItem, ReportNarrativeContext
from app.schemas.student_strengths import StrengthCandidate
from app.services.bigfive_content import relative_bands
from app.services.riasec_content import riasec_strength_phrases
from app.services.thinking_style_content import thinking_style_notes

# Fixed order for deterministic top-N selection — same tie-break convention
# as riasec_service.HOLLAND_ORDER (equal scores must not depend on dict
# iteration order).
_THINKING_STYLE_ORDER: list[str] = ["creative_think", "systematic", "strategic", "practical"]
_TOP_THINKING_STYLES = 2


def _interest_evidence(strengths: list[str]) -> list[EvidenceItem]:
    """Top RIASEC letters. Text is the fuller RIASEC_STRENGTH_PHRASES
    sentence (fallback strength-card material), not the bare label —
    interest_map (all 6 spheres, not just these vetted top ones) uses the
    bare name instead, built separately from the full profile."""
    phrases = riasec_strength_phrases()
    return [
        EvidenceItem(source_id=f"riasec:{key}", source_type="riasec_category", text=phrases[key])
        for key in strengths
        if key in phrases
    ]


def _personality_evidence(
    personality_profile: dict[str, float], personality_notes: dict[str, str]
) -> list[EvidenceItem]:
    """Only traits in the "high" band (pronounced relative to the student's
    own five-trait average — bigfive_content.relative_bands) — a "medium" or
    "low" tiered note is honest, not a strength, and doesn't belong in a
    strengths-evidence catalog."""
    bands = relative_bands(personality_profile)
    return [
        EvidenceItem(source_id=f"personality:{trait}", source_type="personality", text=personality_notes[trait])
        for trait in personality_profile
        if bands.get(trait) == "high" and trait in personality_notes
    ]


def _motivation_evidence(motivation_top: list[str], motivation_highlights: list[str]) -> list[EvidenceItem]:
    # motivation_top/motivation_highlights are already 1:1 by construction
    # (motivation_content.highlight_phrases builds highlights from top, in
    # order) regardless of which input-flow produced motivation_top.
    return [
        EvidenceItem(source_id=f"motivation:{category}", source_type="motivation", text=text)
        for category, text in zip(motivation_top, motivation_highlights)
    ]


def _thinking_style_evidence(thinking_style: dict[str, float]) -> list[EvidenceItem]:
    # `> 0`, not just "top 2 regardless": with no real signal (missing key,
    # or a genuine 0.0), ranking by -value alone would still confidently
    # hand out two "top" styles that don't reflect anything measured —
    # exactly the kind of fabricated fact this catalog exists to prevent.
    candidates = [key for key in _THINKING_STYLE_ORDER if thinking_style.get(key, 0.0) > 0]
    ranked = sorted(
        candidates,
        key=lambda key: (-thinking_style[key], _THINKING_STYLE_ORDER.index(key)),
    )
    return [
        EvidenceItem(source_id=f"thinking_style:{key}", source_type="thinking_style", text=thinking_style_notes()[key])
        for key in ranked[:_TOP_THINKING_STYLES]
    ]


def build_report_narrative_context(
    *,
    strengths: list[str],
    personality_profile: dict[str, float],
    personality_notes: dict[str, str],
    thinking_style: dict[str, float],
    motivation_top: list[str],
    motivation_highlights: list[str],
    strength_candidates: list[StrengthCandidate] | None = None,
) -> ReportNarrativeContext:
    """Everything a narrative-generation prompt, its validator, and the
    deterministic fallback are allowed to know about this student.

    Deliberately has no parameter for raw profile/big_five/motivation
    scores, careers[].match_score, or meta.aversion — they simply aren't
    accepted here, so there's nothing for a future caller to accidentally
    forward into the LLM context."""
    evidence = _interest_evidence(strengths)
    evidence += _personality_evidence(personality_profile, personality_notes)
    evidence += _motivation_evidence(motivation_top, motivation_highlights)
    evidence += _thinking_style_evidence(thinking_style)

    # "Сильные стороны" cite only these vetted candidates — never the
    # evidence above, each of which has its own section (PRO-432).
    return ReportNarrativeContext(evidence=evidence, strength_candidates=list(strength_candidates or []))


def unknown_source_ids(context: ReportNarrativeContext, claimed_ids: list[str]) -> set[str]:
    """What a narrative-generation validator calls to reject an LLM output
    that cites a source_id not present in the catalog it was actually given
    — the LLM claiming a fact that doesn't exist in `context`."""
    known = {item.source_id for item in context.evidence} | {c.source_id for c in context.strength_candidates}
    return {ref for ref in claimed_ids if ref not in known}
