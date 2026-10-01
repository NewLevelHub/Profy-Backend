"""Structured output contract for the psychologist-view AI analysis — the
JSON shape app/prompts/psych_ai_analysis.py asks the model for, and what
app/services/psych_ai_analysis_validator.py checks before it's persisted
onto AnalysisResult.psych_ai_analysis.

Unlike app.schemas.report_narrative (student-facing, evidence-cited, never
names a profession), this is specialist-only: the reader is a psychologist,
so raw scores/labels are fine to reference directly, and — the one hard
requirement — `recommended_profession` MUST be one of the assessment's own
already-computed `careers` (never a profession the model invents), verified
by the validator against `PsychAiAnalysisContext.careers`, not just asked
for in the prompt."""
from pydantic import BaseModel


class BlockAnalysisItem(BaseModel):
    # Matches one of PsychAiAnalysisContext.blocks[i].key — which section of
    # the report this commentary is about (e.g. "riasec", "big_five",
    # "eysenck", "belbin"...).
    block: str
    # ~2 sentences of psychologist-facing commentary on this block alone.
    text: str


class ProfessionRecommendation(BaseModel):
    slug: str
    name: str
    # Why THIS one, among the student's own top professions — grounded in
    # the raw data across blocks, not just restating the algorithm's own
    # `why` for that career.
    reasoning: str


class PsychAiAnalysisOutput(BaseModel):
    block_analyses: list[BlockAnalysisItem]
    # Up to ~7 sentences synthesizing everything for the psychologist.
    final_summary: str
    # None when the assessment has no career list to pick from at all
    # (`careers` empty) — the model is never asked to invent one in that case.
    recommended_profession: ProfessionRecommendation | None = None
