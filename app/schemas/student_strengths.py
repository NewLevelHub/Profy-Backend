"""Contracts of the student-facing «Сильные стороны» selection (PRO-432).

`StrengthInputs` is everything the selection reads — already-scored,
locale-free results of every finished instrument. `StrengthCandidate` is one vetted
card: the methodology decides it (app/services/student_strengths_service.py),
the LLM may only rephrase its title/description.
"""
from typing import Literal

from pydantic import BaseModel

from app.schemas.astur import AsturResultSnapshot

# How the card is grounded — shown to the student as a badge, and what the
# narrative validator checks the wording against (an `interest` must never
# read as a proven ability).
StrengthBasis = Literal["task_result", "self_report", "cross_signal", "interest"]
STRENGTH_BASES: tuple[str, ...] = ("task_result", "self_report", "cross_signal", "interest")

StrengthDomain = Literal[
    "cognitive", "activity", "team", "social", "self_regulation", "experience", "interest"
]

StrengthSourceType = Literal[
    "astur",
    "professional_types",
    "belbin",
    "empathy",
    "social_confidence",
    "elers",
    "riasec",
    "onboarding",
    "cross",
]


class OnboardingArtifact(BaseModel):
    id: str
    value: str


class StrengthInputs(BaseModel):
    # RIASEC types that clear the "high" bar and aren't contradicted by the
    # student's own aversion answers — interest only, never ability.
    riasec_confirmed: list[str] = []
    ddo_interest: dict[str, int] | None = None
    ddo_abilities: dict[str, int] | None = None
    belbin_role_totals: dict[str, int] | None = None
    astur: AsturResultSnapshot | None = None
    empathy_channels: dict[str, int] | None = None
    empathy_level: str | None = None
    confidence_level: str | None = None
    elers_level: str | None = None
    # Eysenck lie scale above its cut-off — self-reports are not read as
    # confident strengths then.
    lie_flagged: bool = False
    subjects_liked: list[str] = []
    subjects_easy: list[str] = []
    artifacts: list[OnboardingArtifact] = []


class StrengthCandidate(BaseModel):
    # Stable, locale-free id the narrative cites (never shown to the student).
    source_id: str
    source_type: StrengthSourceType
    domain: StrengthDomain
    basis: StrengthBasis
    content_key: str
    # Underlying facts; one fact never backs two cards.
    evidence_ids: list[str]
    quality_flags: list[str] = []
    # 1 = strongest grounding (task result / cross-test signal) … 7 = interest.
    priority: int
    title: str
    description: str
    try_now: str | None = None
