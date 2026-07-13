import uuid

from pydantic import BaseModel

# Direction roadmap runs on 4 stages instead of the goal roadmap's 5 horizons.
DIRECTION_HORIZONS = ["months_3", "months_6", "months_9", "months_12"]


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


class RoadmapTrack(BaseModel):
    """One of the two parallel tracks inside a stage."""

    focus: str
    tasks: list[RoadmapTask]


class DirectionStage(BaseModel):
    horizon: str
    title: str
    profile_track: RoadmapTrack     # deepens the direction's core skill
    growth_track: RoadmapTrack      # targets the student's weak spot
    # Set from months_9 on, where the two tracks converge into one project.
    integration_project: str | None = None


class RoadmapTarget(BaseModel):
    role: str                       # who the student is working towards becoming
    why: str                        # why it fits *this* student
    horizon_years: int


class GrowthFocus(BaseModel):
    weakness: str                   # the weak spot the growth track attacks
    why_it_matters: str             # why it would hold them back in this direction


class UniversityTrack(BaseModel):
    specialties: list[str]
    prepare: list[str]


class DirectionRoadmapResponse(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    direction_slug: str
    direction_name: str
    target: RoadmapTarget
    growth_focus: GrowthFocus
    stages: list[DirectionStage]
    skills_to_build: list[str]
    subjects_to_focus: list[str]
    university_track: UniversityTrack

    model_config = {"from_attributes": True}


class GenerateDirectionRoadmapRequest(BaseModel):
    assessment_id: uuid.UUID
    direction_slug: str
