"""StudentContext: the single, complete input bundle for direction-roadmap
generation.

Built from real profile columns, AssessmentSession.belief / Direction.profile,
plus two genuinely *measured* student signals also shown on the /results page:
- axis_matches / axis_growth_areas — the student's own per-axis signal (see
  result_service.child_axis_scores), not just what the direction's ideal
  profile looks like. `strengths` (below) stays direction-shaped ("what this
  direction values"); axis_matches/axis_growth_areas are student-shaped
  ("what we actually measured about this student on those same axes").
- subject_readiness — per-subject level/interest/is_strength from the
  subject-readiness mini-quiz (see subject_readiness_service), when the
  student has completed one for this direction.

Both are optional/empty when the underlying signal doesn't exist yet (no
touched axes overlap this direction, or the mini-quiz wasn't taken) — the
prompt is written to fall back to weaker, self-reported signals in that case
rather than treat absence as "no evidence exists".
"""
from pydantic import BaseModel


class ContextArtifact(BaseModel):
    type: str   # hobby / club / sport / achievement / …
    value: str


class SubjectReadinessScore(BaseModel):
    subject: str
    level: int
    interest: int
    is_strength: bool


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
    # Direction.profile) — this is what the DIRECTION values, not a measured
    # fact about the student. See axis_matches for the student's own signal. ───
    strengths: list[str] = []

    # ─── Real per-axis student signal (result_service.child_axis_scores),
    # restricted to axes this direction actually needs (profile > 0). Empty
    # when the session's questions never touched an axis this direction
    # needs — no fake neutral score is ever substituted. ───
    axis_matches: dict[str, float] = {}
    axis_growth_areas: dict[str, float] = {}

    # ─── Subject-readiness mini-quiz result for this direction, if taken
    # (subject_readiness_service) — measured level/interest/is_strength per
    # required subject, independent of the student's self-reported
    # subjects_liked/disliked/easy/hard above. ───
    subject_readiness: list[SubjectReadinessScore] = []

    # ─── Top leaf directions by AssessmentSession.belief (name -> normalized
    # score, sum over all leaves ~= 1.0) — what the student leans toward
    # overall, not just the direction being planned. ───
    leaning_directions: dict[str, float] = {}

    # ─── Leaf directions explicitly rejected via reject_leaf during the test. ───
    rejected_directions: list[str] = []
