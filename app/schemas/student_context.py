"""StudentContext: the single, complete input bundle for direction-roadmap
generation.

Built entirely from the axis-driven Akinator engine's persisted state — there
is no separate scoring pass anymore, so every field here is either a real
profile column or derived from AssessmentSession.belief / Direction.profile.
There is no per-axis score retained for the student (belief only tracks
likelihood per leaf direction, not per axis — see
result_service.matched_axes_for for the same constraint), so "strengths" is
read off the target direction's own profile rather than off the student.
"""
from pydantic import BaseModel


class ContextArtifact(BaseModel):
    type: str   # hobby / club / sport / achievement / …
    value: str


class StudentContext(BaseModel):
    # ─── Profile ───
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

    # ─── Axes the target direction weighs most (label_ru, value >= +1 in
    # Direction.profile) — read as "what draws the student to this
    # direction", since we have no independent per-axis score for them. ───
    strengths: list[str] = []

    # ─── Top leaf directions by AssessmentSession.belief (name -> normalized
    # score, sum over all leaves ~= 1.0) — what the student leans toward
    # overall, not just the direction being planned. ───
    leaning_directions: dict[str, float] = {}

    # ─── Leaf directions explicitly rejected via reject_leaf during the test. ───
    rejected_directions: list[str] = []
