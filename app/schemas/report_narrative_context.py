"""ReportNarrativeContext: the safe evidence catalog for /result narrative
generation (summary, strength cards, thinking-style notes, career "why").

Deliberately NOT StudentContext (app/schemas/student_context.py) — that
bundle still carries raw profile percentages, RIASEC/MI codes and
match_score for the roadmap/direction-inquiry prompts (a different, more
permissive consumer). Nothing here ever carries a number: every fact is a
pre-labeled, already-safe phrase with a stable source_id, so a narrative
prompt, its output validator, and the deterministic fallback can all share
exactly the same allow-list instead of each deciding independently what's
safe to say.
"""
from typing import Literal

from pydantic import BaseModel


class EvidenceItem(BaseModel):
    source_id: str
    source_type: Literal[
        "mi_category",
        "riasec_category",
        "personality",
        "motivation",
        "thinking_style",
        "subject_liked",
        "subject_easy",
        "artifact",
    ]
    text: str


class ReportNarrativeContext(BaseModel):
    age_group: str
    interest_instrument: Literal["mi", "riasec"]
    evidence: list[EvidenceItem] = []
