"""Builds the safe evidence catalog (ReportNarrativeContext) that report
narrative generation, its output validator, and the deterministic fallback
are all meant to share — see app/schemas/report_narrative_context.py for why
this exists instead of reusing StudentContext.

Pure function, no DB access: called from report_service.build_report with
values it has already computed in memory (scores aren't re-fetched from a
stored AnalysisResult, since this runs before that row exists). This is
also why it never touches a response table regardless of which motivation
input-flow produced its inputs — junior/middle answer Harter pairs
(motivation_pair_service), senior answers MOST/LEAST triplets
(motivation_service), but both are already collapsed into the same
motivation_top/motivation_highlights shape before this function ever runs,
so it has nothing flow-specific to know about.
"""
from app.models.artifact import Artifact
from app.models.profile import AgeGroup
from app.schemas.report_narrative_context import EvidenceItem, ReportNarrativeContext
from app.services.bigfive_content import is_high_tier
from app.services.mi_content import MI_STRENGTH_PHRASES
from app.services.riasec_content import RIASEC_STRENGTH_PHRASES
from app.services.thinking_style_content import THINKING_STYLE_NOTES

# Fixed order for deterministic top-N selection — same tie-break convention
# as riasec_service.HOLLAND_ORDER (equal scores must not depend on dict
# iteration order).
_THINKING_STYLE_ORDER: list[str] = ["creative_think", "systematic", "strategic", "practical"]
_TOP_THINKING_STYLES = 2


def _interest_evidence(age_group: AgeGroup, strengths: list[str]) -> tuple[str, list[EvidenceItem]]:
    """Junior's top interests are MI categories; middle/senior's are RIASEC
    letters — never both, and never the other age group's instrument. Text
    is the fuller *_STRENGTH_PHRASES sentence (fallback strength-card
    material), not the bare *_LABELS type name — interest_map (all 6/8
    spheres, not just these vetted top ones) uses the bare name instead,
    built separately in report_fallback.py from the full profile."""
    if age_group == AgeGroup.junior:
        phrases, source_type, instrument = MI_STRENGTH_PHRASES, "mi_category", "mi"
    else:
        phrases, source_type, instrument = RIASEC_STRENGTH_PHRASES, "riasec_category", "riasec"

    items = [
        EvidenceItem(source_id=f"{instrument}:{key}", source_type=source_type, text=phrases[key])
        for key in strengths
        if key in phrases
    ]
    return instrument, items


def _personality_evidence(
    personality_profile: dict[str, float], personality_notes: dict[str, str]
) -> list[EvidenceItem]:
    """Only high-tier traits — a "mid" or "low" tiered note is honest, not a
    strength, and doesn't belong in a strengths-evidence catalog."""
    return [
        EvidenceItem(source_id=f"personality:{trait}", source_type="personality", text=personality_notes[trait])
        for trait, value in personality_profile.items()
        if is_high_tier(value) and trait in personality_notes
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
        EvidenceItem(source_id=f"thinking_style:{key}", source_type="thinking_style", text=THINKING_STYLE_NOTES[key])
        for key in ranked[:_TOP_THINKING_STYLES]
    ]


def _subject_evidence(subjects: list[str], source_type: str) -> list[EvidenceItem]:
    return [
        EvidenceItem(source_id=f"{source_type}:{name}", source_type=source_type, text=name)
        for name in subjects
    ]


def _artifact_evidence(artifacts: list[Artifact]) -> list[EvidenceItem]:
    return [
        EvidenceItem(source_id=f"artifact:{artifact.id}", source_type="artifact", text=artifact.value)
        for artifact in artifacts
    ]


def build_report_narrative_context(
    *,
    age_group: AgeGroup,
    strengths: list[str],
    personality_profile: dict[str, float],
    personality_notes: dict[str, str],
    thinking_style: dict[str, float],
    motivation_top: list[str],
    motivation_highlights: list[str],
    subjects_liked: list[str],
    subjects_easy: list[str],
    artifacts: list[Artifact],
) -> ReportNarrativeContext:
    """Everything a narrative-generation prompt, its validator, and the
    deterministic fallback are allowed to know about this student.

    Deliberately has no parameter for raw profile/big_five/motivation
    scores, careers[].match_score, or meta.aversion — they simply aren't
    accepted here, so there's nothing for a future caller to accidentally
    forward into the LLM context."""
    instrument, evidence = _interest_evidence(age_group, strengths)
    evidence += _personality_evidence(personality_profile, personality_notes)
    evidence += _motivation_evidence(motivation_top, motivation_highlights)
    evidence += _thinking_style_evidence(thinking_style)
    evidence += _subject_evidence(subjects_liked, "subject_liked")
    evidence += _subject_evidence(subjects_easy, "subject_easy")
    evidence += _artifact_evidence(artifacts)

    return ReportNarrativeContext(
        age_group=age_group.value,
        interest_instrument=instrument,
        evidence=evidence,
    )


def unknown_source_ids(context: ReportNarrativeContext, claimed_ids: list[str]) -> set[str]:
    """What a narrative-generation validator calls to reject an LLM output
    that cites a source_id not present in the catalog it was actually given
    — the LLM claiming a fact that doesn't exist in `context`."""
    known = {item.source_id for item in context.evidence}
    return {ref for ref in claimed_ids if ref not in known}
