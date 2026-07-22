import uuid

from pydantic import BaseModel


class RoadmapResource(BaseModel):
    """A concrete item from the app's content base (book, course, club, material).

    The catalogue does not exist yet, so this stays empty: the LLM is not allowed
    to invent entries. The field is here so the client can render resources the
    moment the catalogue lands, without an API change."""

    title: str
    kind: str
    url: str | None = None


class RoadmapTask(BaseModel):
    text: str
    # What to actually do, where to start, and how to know it's done. The student
    # must not have to google the task to understand it. Optional: the legacy goal
    # roadmap does not produce it.
    description: str | None = None
    category: str
    priority: int
    resources: list[RoadmapResource] = []


class RoadmapMilestone(BaseModel):
    horizon: str
    title: str
    tasks: list[RoadmapTask]


class RoadmapResponse(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    goal: str
    milestones: list[RoadmapMilestone]

    model_config = {"from_attributes": True}


# ─── Direction roadmap ─────────────────────────────────────────────────────────
#
# Two layers: real curated/DB-backed facts (profession_options come from
# Direction.professions, subjects_now weights from Direction.subjects_required,
# university_requirements from real Program/University rows) plus a thin LLM
# personalization layer (the `why`/`note` text, growth_focus, starter_actions
# fallback) grounded in the student's measured signal. See
# app/services/roadmap_builder.py and app/prompts/direction_roadmap.py.


class ProfessionOption(BaseModel):
    title: str                      # one of Direction.professions verbatim
    # Set only when a real signal genuinely singles this one out among the
    # direction's other professions; null when just listed as an open option —
    # the model must not dress a guess as certainty (see roadmap_builder tests).
    why: str | None = None


class SubjectPriority(BaseModel):
    subject: str
    weight: int                     # from Direction.subjects_required — backend-attached, not LLM
    note: str                       # 1-sentence personalized note, same evidence rules as growth_focus


class GrowthFocus(BaseModel):
    weakness: str                   # the weak spot growth work should attack
    why_it_matters: str             # why it would hold them back in this direction
    # Which signal in the student's own data this was derived from. Forces the
    # model to ground the claim instead of inventing a plausible-sounding flaw,
    # and is shown in the UI so the student can see why we said it.
    evidence: str = ""


class UniversityRequirement(BaseModel):
    """Real admission facts for one program — backend-populated from
    Program.requirements, never touched by the LLM (see
    roadmap_builder._university_requirements_for)."""

    program_name: str
    university_name: str
    city: str
    exams: list[str] = []
    admission_requirements: list[str] = []
    admission_summary: str = ""


class DirectionRoadmapResponse(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    direction_slug: str
    direction_name: str
    profession_options: list[ProfessionOption]
    subjects_now: list[SubjectPriority]
    starter_actions: list[str]
    growth_focus: GrowthFocus
    skills_to_build: list[str]
    university_requirements: list[UniversityRequirement]

    model_config = {"from_attributes": True}


class GenerateDirectionRoadmapRequest(BaseModel):
    assessment_id: uuid.UUID
    direction_slug: str
