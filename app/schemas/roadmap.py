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
    # Legacy field from when a single milestone list mixed multiple
    # directions' tasks together, tagged by which RecommendedPath.key they
    # belonged to. Superseded 2026-08-18 by RecommendedPath.milestones (each
    # path now carries its own fully independent milestone list, so nothing
    # needs tagging any more) — kept only so old stored rows still parse.
    # Always null on anything generated going forward.
    path: str | None = None


class RoadmapMilestone(BaseModel):
    horizon: str
    title: str
    outcome: str = ""
    tasks: list[RoadmapTask]


class RecommendedPath(BaseModel):
    """A concrete leading direction offered to an explore/unsure student —
    entirely self-contained: its own 5 milestones, not mixed with any other
    path's tasks (product decision 2026-08-18 — mixing them in one list read
    as an incoherent plan with no clear goal). 1-2 of these for goal in
    (explore, unsure); empty for profession/university, which already have a
    single confirmed direction (that plan stays in RoadmapResponse.milestones)."""

    key: str                 # "A" / "B" — stable id, no longer referenced by tasks
    label: str                # e.g. "Робототехника"
    why: str                  # why this fits *this* student, grounded in their profile
    future_benefit: str       # what it concretely leads to later
    milestones: list[RoadmapMilestone] = []


class RoadmapResponse(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    goal: str
    # The plan itself when there's one direction (profession/university, or
    # explore/unsure with a single clear winner). When recommended_paths has
    # 2 entries, this mirrors recommended_paths[0].milestones so any caller
    # that only reads .milestones still gets one complete, coherent plan —
    # the real UI should switch to rendering recommended_paths[*].milestones
    # as separate tabs once there's more than one.
    milestones: list[RoadmapMilestone]
    focus_summary: str | None = None
    recommended_paths: list[RecommendedPath] = []
    # Hand-verified catalogue entries (app/data/resource_catalog.py), matched
    # deterministically off the top matched direction — never LLM-picked.
    # Shown as a single "Дополнительный источник" block at the end.
    additional_resources: list[RoadmapResource] = []

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


class SubjectFocusItem(BaseModel):
    """School-subject development for one stage, tied to the student's grade.

    months_3 topics are always base/gap-closing; months_6/9/12 topics track
    the student's actual grade going forward and must not repeat across
    stages. Sourced from the LLM's own curriculum knowledge — no curriculum
    database backs this."""

    subject: str             # e.g. "математика"
    topics: list[str]        # concrete topic names, not the whole subject
    why: str = ""             # why this topic matters for this stage/direction


class DirectionStage(BaseModel):
    horizon: str
    title: str
    # What the student will have by the end of the stage, and how it moves them
    # towards the target role. Makes the plan explain itself.
    outcome: str = ""
    steps: list[RoadmapStep] = []
    subject_focus: list[SubjectFocusItem] = []
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


class ProgramGrant(BaseModel):
    name: str
    amount: str | None = None
    conditions: str | None = None


class UniversityRequirement(BaseModel):
    """Backend-populated, per-program facts from `Program`/`University` — never
    asked of the LLM and not part of `DIRECTION_ROADMAP_SCHEMA`. Populated only
    when `context.goal == "university"`; every other goal gets an empty list.

    `None` means "no data for this field" — it is never used to mean "not
    required". `portfolio_needed=False` is a real, known fact and must stay
    distinguishable from "we don't know" (`None`).

    `min_ent_threshold`/`admission_scores_2026`/`notes` are disjoint by seed
    source (scripts/apply_grant_admission_data_2026.py): a program gets EITHER
    a `min_ent_threshold` (no 2026-2027 grant-competition data exists) OR
    `admission_scores_2026` entries (this year's real grant-winning scores),
    rarely both. Both represent the state grant-competition eligibility bar
    (MES RK reference data), not a generic "minimum to enrol at all" —
    labelled accordingly in the UI, not as a plain admission minimum.
    `notes` (subject-pair hints per specialty) can appear either way. All
    three were previously silently dropped by `_map_program_requirement`
    — programs seeded only with the newer shape reached the LLM with an
    almost-empty requirement block despite having real admission data."""

    program_name: str
    university_name: str
    city: str
    country: str
    website: str | None = None
    # Actual language of instruction (Program.language, e.g. "Английский,
    # немецкий") — always set. Distinct from `language_level` below (a
    # required IELTS/TOEFL band), which is sparse/optional.
    program_language: str
    exams: list[str]
    # Set only when `exams` came back empty AND a general university note
    # keyword-matched this program's own name (see
    # university_requirements._note_hint_for_program) — an inferred hint, not
    # a confirmed per-program fact, and the frontend must label it as such.
    exam_hint_from_notes: str | None = None
    application_deadline: str | None = None
    grants: list[ProgramGrant] = []
    # Required IELTS/TOEFL band (requirements["min_ielts"]) — sparse/optional,
    # NOT the language of instruction (see `program_language` above).
    language_level: str | None = None
    portfolio_needed: bool | None = None
    required_documents: list[str] | None = None
    min_ent_threshold: int | None = None
    min_gpa: float | None = None
    min_sat: int | None = None
    extracurriculars: list[str] = []
    admission_scores_2026: list[str] = []
    notes: list[str] = []


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
    university_requirements: list[UniversityRequirement] = []
    # Hand-verified catalogue entries (app/data/resource_catalog.py), matched
    # deterministically off this direction's own name/skills/subjects — never
    # LLM-picked. Shown as a single "Дополнительный источник" block at the end.
    additional_resources: list[RoadmapResource] = []
    # Set only when this plan was built from a specific chosen Program
    # (goal="university" generate-by-program path). None otherwise.
    program_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class GenerateDirectionRoadmapRequest(BaseModel):
    assessment_id: uuid.UUID
    direction_slug: str


class GenerateDirectionRoadmapForProgramRequest(BaseModel):
    assessment_id: uuid.UUID
    program_id: uuid.UUID
