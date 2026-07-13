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

# What a step works on. Steps are tagged rather than grouped into fixed tracks,
# so the model decides how much of each a given stage actually needs.
STEP_TRACKS = ["profile", "growth", "integration"]


class RoadmapStep(BaseModel):
    text: str                       # short name of the step
    description: str                # what to do, where to start, how to know it's done
    track: str                      # profile | growth | integration
    category: str
    priority: int                   # 1 = do first
    resources: list[RoadmapResource] = []


class DirectionStage(BaseModel):
    horizon: str
    title: str
    # What the student will have by the end of the stage, and how it moves them
    # towards the target role. Makes the plan explain itself.
    outcome: str = ""
    steps: list[RoadmapStep] = []
    # Set from months_9 on, where the profile and growth work converge.
    integration_project: str | None = None


class RoadmapTarget(BaseModel):
    role: str                       # who the student is working towards becoming
    why: str                        # why it fits *this* student
    horizon_years: int


class GrowthFocus(BaseModel):
    weakness: str                   # the weak spot the growth steps attack
    why_it_matters: str             # why it would hold them back in this direction
    # Which signal in the student's own data this was derived from. Forces the
    # model to ground the claim instead of inventing a plausible-sounding flaw,
    # and is shown in the UI so the student can see why we said it.
    evidence: str = ""


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
