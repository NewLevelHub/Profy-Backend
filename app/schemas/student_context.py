"""StudentContext: the single, complete input bundle for report/roadmap generation.

This is what the roadmap LLM (Phase 3) receives. It deliberately gathers data
that was collected but previously unused — city/country, school subjects, stated
values (money/freedom/…), goal-clarification signals, university preferences —
so generation can actually personalize on them.
"""
from pydantic import BaseModel


class ContextArtifact(BaseModel):
    type: str   # hobby / club / sport / achievement / …
    value: str


class ContextDirection(BaseModel):
    slug: str
    name: str
    match_score: int
    description: str = ""
    professions: list[str] = []
    skills_needed: list[str] = []
    subjects_to_develop: list[str] = []
    first_steps: list[str] = []


class StudentContext(BaseModel):
    # ─── Profile (incl. previously-unused fields) ───
    name: str
    age: int
    age_group: str
    grade: int
    city: str
    country: str
    language: str
    subjects_liked: list[str] = []
    subjects_disliked: list[str] = []
    subjects_easy: list[str] = []
    subjects_hard: list[str] = []

    # ─── Clubs / sections / hobbies / achievements ───
    artifacts: list[ContextArtifact] = []

    # ─── Chosen goal ───
    goal: str

    # ─── Analysis (from the stored report) ───
    summary: str = ""
    strengths: list[str] = []
    interests_map: dict[str, float] = {}
    thinking_style: dict[str, float] = {}
    motivation: list[str] = []
    wellbeing_zones: list[str] = []

    # ─── Previously-dead raw signals, now surfaced ───
    values: dict[str, float] = {}                 # money / freedom / stability / …
    goal_clarification: dict[str, float] = {}     # goal_* signals
    university_preferences: dict[str, str] = {}   # pref_* (senior + university goal)

    # ─── Age-appropriate matched directions ───
    directions: list[ContextDirection] = []
