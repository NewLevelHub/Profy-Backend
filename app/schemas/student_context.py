"""StudentContext: the single, complete input bundle for report/roadmap generation.

This is what the roadmap/direction-inquiry LLM prompts receive. It deliberately
gathers data that was collected but previously unused — city/country, school
subjects — so generation can actually personalize on them.
"""
from pydantic import BaseModel


class ContextArtifact(BaseModel):
    type: str   # hobby / club / sport / achievement / …
    value: str


class ContextCareer(BaseModel):
    slug: str
    name: str
    holland_code: str
    match_score: int
    description: str = ""
    professions: list[str] = []
    skills_needed: list[str] = []
    subjects_to_develop: list[str] = []
    first_steps: list[str] = []


class ContextInquiry(BaseModel):
    """Stored outcome of the AI direction-fit inquiry for the chosen direction."""

    direction_slug: str
    readiness: str
    fit_summary: str
    note: str
    # Statements the student rated low (1-2) / high (4-5) on the 5-point scale.
    # The low ones are the sharpest evidence of what holds them back here.
    low_signals: list[str] = []
    high_signals: list[str] = []


class StudentContext(BaseModel):
    # ─── Profile (incl. previously-unused fields) ───
    name: str
    age: int
    age_group: str
    grade: int
    city: str
    country: str
    language: str
    locale: str = "ru"
    subjects_liked: list[str] = []
    subjects_disliked: list[str] = []
    subjects_easy: list[str] = []
    subjects_hard: list[str] = []

    # ─── Clubs / sections / hobbies / achievements ───
    artifacts: list[ContextArtifact] = []

    # ─── Chosen goal ───
    goal: str

    # ─── Analysis (from the stored RIASEC report) ───
    summary: str = ""
    profile: dict[str, float] = {}   # {"R": 82.0, ...}
    code: list[str] = []             # ["R", "I", "A"]
    strengths: list[str] = []        # letters
    weaknesses: list[str] = []       # letters

    # ─── Big Five / motivation — safe, display-ready derived layer only.
    # AnalysisResult.big_five/motivation (raw scores) are admin-only
    # (app/models/analysis_result.py:30,33 — ТЗ §18.3: no raw percentages to
    # the student) and are deliberately NOT exposed here. These five fields
    # mirror what the report already shows the student (bigfive_content.py,
    # report_service.py:176), so prompts can use them without any risk of a
    # raw score leaking into student-facing text.
    personality_profile: dict[str, float] = {}   # 5 traits, display-ready (N flipped to emotional_stability)
    personality_notes: dict[str, str] = {}        # 1 tiered RU phrase per trait, high/low/mid-honest, never a number
    thinking_style: dict[str, float] = {}         # {creative_think, systematic, strategic, practical}
    motivation_top: list[str] = []                # ["interest", "creation"] — categorical, not a score
    motivation_highlights: list[str] = []          # RU phrases, "что тебя драйвит"

    # ─── Matched careers ───
    careers: list[ContextCareer] = []

    # ─── Inquiry outcome for the direction being planned (when there is one) ───
    inquiry: ContextInquiry | None = None
