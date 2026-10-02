"""Builds the raw-data bundle the psychologist-view AI analysis prompt reads
from. Unlike report_narrative_context.py (student-facing, hand-curated
"safe evidence" with no raw numbers), this hands the model whatever's
actually on the report/new_tests objects — the reader is a professional,
not a child, so there's no need to pre-abstract facts into safe phrases."""
import hashlib

from pydantic import BaseModel
from pydantic_core import to_jsonable_python

from app.schemas.new_tests import NewTestsSections
from app.schemas.result_v2 import ResultResponseV2

# block key -> human label shown to the model (and, 1:1, to the psychologist
# in the eventual report UI) — the single source of truth for both.
BLOCK_LABELS: dict[str, str] = {
    "interests": "Карта интересов",
    "personality": "Личность (Big Five)",
    "thinking_style": "Стиль мышления",
    "motivation": "Мотивация",

    "psychoemotional": "Психоэмоциональное состояние (МЦВ)",
    "professional_types": "ДДО (интересы и способности)",
    "temperament": "Темперамент (Айзенк)",
    "aspiration_level": "Мотивация к успеху (Элерс)",
    "empathy_confidence": "Эмпатия и соц. уверенность",
    "team_role": "Командная роль (Белбин)",
    # PRO-427: percent of study-type tasks, not intelligence — the label is
    # what the model reads first, so it must not invite IQ-style claims.
    "intelligence": "Когнитивные навыки (учебные задания)",
}


class BlockData(BaseModel):
    key: str
    label: str
    facts: dict


class CareerOption(BaseModel):
    slug: str
    name: str
    # «Почему тебе подходит» exactly as the student reads it — already one
    # text over every concrete fact ↔ profession reason.
    why: str


class PsychAiAnalysisContext(BaseModel):
    student_name: str
    # TODAY's profile age/grade — context for the other blocks. The АСТУР
    # block carries its own age/grade at completion inside its facts; the
    # two are never mixed (the attempt was taken at its own age).
    current_age: int | None = None
    current_grade: int | None = None
    blocks: list[BlockData]
    # The student's own already-ranked top professions (report.careers) —
    # the ONLY professions the model is allowed to recommend from. When
    # empty (no matching direction), the prompt/
    # validator both treat an empty list as "don't recommend a profession
    # at all", never as license to invent one.
    careers: list[CareerOption]


def _intelligence_facts(section) -> dict:
    """The frozen АСТУР snapshot as the model should read it: scored
    percents and observed quick-instruction counts, protocol quality and the
    age/grade at the time of the attempt. No run/version ids (noise for the
    model) — only whether the attempt is a legacy one."""
    return section.model_dump(
        mode="json",
        exclude={"run_id", "bank_version", "scoring_version", "completed_at"},
        exclude_none=True,
    )


def build_context(
    report: ResultResponseV2,
    new_tests: NewTestsSections,
    *,
    student_name: str,
    current_age: int | None = None,
    current_grade: int | None = None,
) -> PsychAiAnalysisContext:
    blocks: list[BlockData] = []

    def add(key: str, facts: dict) -> None:
        # Facts go into the prompt through plain json.dumps, so they must be
        # JSON-native here — e.g. the psychoemotional block's completed_at
        # (and each history item's) is a datetime; tuples become lists.
        # Converting in this one place keeps a new datetime/UUID field on any
        # section from silently killing the whole AI analysis again. The
        # fingerprint is unaffected: model_dump_json renders these the same.
        blocks.append(BlockData(key=key, label=BLOCK_LABELS[key], facts=to_jsonable_python(facts)))

    if report.interest_map:
        add("interests", {"interest_map": [i.model_dump() for i in report.interest_map]})
    if report.personality_notes:
        add("personality", {"notes": [n.model_dump() for n in report.personality_notes]})
    if report.thinking_style_notes:
        add("thinking_style", {"notes": [n.model_dump() for n in report.thinking_style_notes]})
    if report.motivation_highlights:
        add("motivation", {"highlights": report.motivation_highlights})

    if report.psychoemotional:
        # The specialist-facing interpretation texts (PRO-448) stay out: the
        # model reads the metrics, and leaving them out keeps the context
        # fingerprint of already cached analyses unchanged.
        add("psychoemotional", report.psychoemotional.model_dump(exclude={"interpretation"}))

    if new_tests.professional_types:
        add("professional_types", new_tests.professional_types.model_dump(exclude_none=True))
    if new_tests.temperament:
        add("temperament", new_tests.temperament.model_dump(exclude_none=True))
    if new_tests.aspiration_level:
        add("aspiration_level", new_tests.aspiration_level.model_dump(exclude_none=True))
    if new_tests.empathy_confidence:
        add("empathy_confidence", new_tests.empathy_confidence.model_dump(exclude_none=True))
    if new_tests.team_role:
        add("team_role", new_tests.team_role.model_dump(exclude_none=True))
    if new_tests.intelligence:
        add("intelligence", _intelligence_facts(new_tests.intelligence))

    careers = [CareerOption(slug=c.slug, name=c.name, why=c.why) for c in report.careers]

    return PsychAiAnalysisContext(
        student_name=student_name,
        current_age=current_age,
        current_grade=current_grade,
        blocks=blocks,
        careers=careers,
    )


def fingerprint(context: PsychAiAnalysisContext) -> str:
    """Identity of everything the analysis was generated from. A cached
    analysis is valid only for the exact same inputs — a new completed
    АСТУР attempt, a new scoring version or a changed age all change it.

    The careers' *order* is left out: the analysis's own pick is moved to the
    top of that list (psychologist_service._apply_ai_recommendation),
    and the psychologist may reorder it — neither is new input, and counting
    it would regenerate the analysis (and possibly its pick) on every view."""
    identity = context.model_copy(update={"careers": sorted(context.careers, key=lambda career: career.slug)})
    return hashlib.sha256(identity.model_dump_json().encode("utf-8")).hexdigest()


def has_any_data(context: PsychAiAnalysisContext) -> bool:
    """Nothing to analyze yet — e.g. a report generated before any optional
    extended block (Belbin/АСТУР) was even assigned, on top of a bare-bones
    core result. Callers skip generation entirely in this case rather than
    spending an LLM call on an empty context."""
    return bool(context.blocks)
