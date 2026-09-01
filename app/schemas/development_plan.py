"""Pydantic models for the development plan (план развития).

Nested shape: stage → task → step → action. Phase 1 (skeleton) fills every
level except `PlanStep`/`PlanAction`; phase 2 fills those in per stage. See
app/prompts/development_plan.py for the two LLM JSON schemas and
app/services/development_plan_validation.py for the structural guards.
"""
import uuid
from typing import Literal

from pydantic import BaseModel

from app.schemas.roadmap import UniversityRequirement

ActionKind = Literal["once", "repeat", "project"]
# `language` only appears for foreign universities.
Track = Literal["ent", "profession", "growth", "admission", "language"]

TRACKS: tuple[str, ...] = ("ent", "profession", "growth", "admission", "language")


class PlanAction(BaseModel):
    text: str
    time: str                     # "15 мин" | "~2 часа" | "20 мин/день, 4 недели"
    kind: ActionKind
    count_target: int | None = None   # required when kind == "repeat"


class PlanStep(BaseModel):
    title: str
    actions: list[PlanAction]


class PlanTask(BaseModel):
    track: Track
    title: str
    why: str
    done_when: str
    steps: list[PlanStep] = []     # empty after phase 1, filled after phase 2


class PlanStage(BaseModel):
    slot: str                     # STAGE_SLOTS key, e.g. "autumn_11"
    label: str                    # e.g. "Осень 11 класса"
    outcome: str
    tasks: list[PlanTask]


class PlanTarget(BaseModel):
    role: str
    why: str
    university_name: str
    specialty: str


class PlanGrowth(BaseModel):
    area: str
    why: str
    evidence: str                 # must quote a concrete signal from the student's data


class PlanAboutYou(BaseModel):
    strengths: list[str]
    # null when the student has no pronounced growth point — we don't invent one.
    growth: PlanGrowth | None = None


class AdmissionFacts(UniversityRequirement):
    """Backend-populated facts block. Everything from `map_program_requirement`
    plus the foreign-track extras and provenance. The LLM never writes this."""

    is_foreign: bool = False
    foreign_route: str | None = None      # general per-country text (not per-university)
    language_exam: str | None = None      # "IELTS Academic" | "TOEFL iBT" | None
    source_url: str | None = None
    last_verified: str | None = None      # YYYY-MM-DD from Program/University fact_sources


class DevelopmentPlanResponse(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    program_id: uuid.UUID
    direction_slug: str
    direction_name: str
    is_foreign: bool
    target: PlanTarget
    about_you: PlanAboutYou
    stages: list[PlanStage]
    admission_facts: AdmissionFacts

    model_config = {"from_attributes": True}


class GenerateDevelopmentPlanRequest(BaseModel):
    assessment_id: uuid.UUID
    program_id: uuid.UUID
