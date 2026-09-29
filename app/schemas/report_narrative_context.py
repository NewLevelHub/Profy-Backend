"""ReportNarrativeContext: the safe evidence catalog for /result narrative
generation (summary, strength cards, thinking-style notes, career "why").

Nothing here ever carries a number: every fact is a
pre-labeled, already-safe phrase with a stable source_id, so a narrative
prompt, its output validator, and the deterministic fallback can all share
exactly the same allow-list instead of each deciding independently what's
safe to say.
"""
from typing import Literal

from pydantic import BaseModel

from app.schemas.student_strengths import StrengthCandidate


class EvidenceItem(BaseModel):
    source_id: str
    source_type: Literal[
        "riasec_category",
        "personality",
        "motivation",
        "thinking_style",
    ]
    text: str


class ReportNarrativeContext(BaseModel):
    evidence: list[EvidenceItem] = []
    # «Сильные стороны» (PRO-432): already chosen by the methodology — the
    # narrative writes exactly one card per candidate and cites nothing else.
    strength_candidates: list[StrengthCandidate] = []
