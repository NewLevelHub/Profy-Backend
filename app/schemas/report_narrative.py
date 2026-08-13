"""Structured output contract for LLM-generated report narrative text — the
JSON shape app/prompts/report_narrative.py asks the model for, and what
app/services/report_narrative_validator.py checks before anything derived
from it could reach a child.

Deliberately separate from app.schemas.admin_result.AdminStrengthCard /
AdminThinkingStyleNote: those are the persisted `{title, description}` shape
(AnalysisResult.strength_cards/thinking_style_notes, migration 0041). This
schema also carries `evidence_ids`, needed only transiently by the validator
to verify every claim traces back to a real
app.schemas.report_narrative_context.EvidenceItem.source_id — evidence_ids
are dropped before persistence, they're not stored.
"""
from typing import Literal

from pydantic import BaseModel


class NarrativeCard(BaseModel):
    title: str
    description: str
    evidence_ids: list[str] = []


class InterestCard(BaseModel):
    """One entry per category of the age group's interest instrument (all 8
    MI categories for junior, all 6 RIASEC letters for middle/senior) — the
    "Карта интересов" section, TZ_Profi.md §18.2/§18.3. `tier` is "strong"
    only for a category the evidence catalog actually flagged as a top
    interest; every other category is "steady" — never framed as a
    weakness, per Приложение C. No evidence_ids: the tier/category pairing
    itself is the fact, checked against the catalog directly rather than by
    citation."""

    category: str
    tier: Literal["strong", "steady"]
    title: str
    description: str


class MotivationNarrative(BaseModel):
    """Single unified shape regardless of whether motivation_top came from
    junior/middle's Harter pairs or senior's MOST/LEAST triplets — the
    evidence catalog already collapsed that distinction before this prompt
    ever runs (see report_narrative_context.py)."""

    title: str
    description: str
    evidence_ids: list[str] = []


class ReportNarrativeOutput(BaseModel):
    summary: str
    strength_cards: list[NarrativeCard]
    interests: list[InterestCard]
    thinking_style_notes: list[NarrativeCard]
    motivation_narrative: MotivationNarrative
    # Junior (TZ_Profi.md §4.1: not career-oriented) must get an empty list.
    # middle/senior get a short, RIASEC-evidence-grounded "why explore this"
    # narrative — never profession names/salaries/university facts, since
    # none of that exists in the evidence catalog to ground it in.
    career_narrative: list[NarrativeCard] = []
    # Shown last on the page, after every other section — ties the report
    # together instead of repeating `summary` (written first, before the
    # reader has seen anything else). Deliberately a plain string, not a
    # NarrativeCard: it's meta-commentary about how the sections relate to
    # each other, not a new individually-cited fact, so it doesn't carry
    # evidence_ids the way a strength/thinking-style card does.
    final_analysis: str
