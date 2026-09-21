"""Builds the raw-data bundle the psychologist-view AI analysis prompt reads
from. Unlike report_narrative_context.py (student-facing, hand-curated
"safe evidence" with no raw numbers), this hands the model whatever's
actually on the report/new_tests objects — the reader is a professional,
not a child, so there's no need to pre-abstract facts into safe phrases."""
from pydantic import BaseModel

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
    "intelligence": "Интеллект (АСТУР)",
}


class BlockData(BaseModel):
    key: str
    label: str
    facts: dict


class CareerOption(BaseModel):
    slug: str
    name: str
    why: str


class PsychAiAnalysisContext(BaseModel):
    student_name: str
    blocks: list[BlockData]
    # The student's own already-ranked top professions (report.careers) —
    # the ONLY professions the model is allowed to recommend from. Empty
    # for junior (TZ_Profi.md §4.1, not career-oriented) — the prompt/
    # validator both treat an empty list as "don't recommend a profession
    # at all", never as license to invent one.
    careers: list[CareerOption]


def build_context(
    report: ResultResponseV2, new_tests: NewTestsSections, *, student_name: str
) -> PsychAiAnalysisContext:
    blocks: list[BlockData] = []

    def add(key: str, facts: dict) -> None:
        blocks.append(BlockData(key=key, label=BLOCK_LABELS[key], facts=facts))

    if report.interest_map:
        add("interests", {"interest_map": [i.model_dump() for i in report.interest_map]})
    if report.personality_notes:
        add("personality", {"notes": [n.model_dump() for n in report.personality_notes]})
    if report.thinking_style_notes:
        add("thinking_style", {"notes": [n.model_dump() for n in report.thinking_style_notes]})
    if report.motivation_highlights:
        add("motivation", {"highlights": report.motivation_highlights})

    if report.psychoemotional:
        add("psychoemotional", report.psychoemotional.model_dump())

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
        add("intelligence", new_tests.intelligence.model_dump(exclude_none=True))

    careers = [CareerOption(slug=c.slug, name=c.name, why=c.why) for c in report.careers]

    return PsychAiAnalysisContext(student_name=student_name, blocks=blocks, careers=careers)


def has_any_data(context: PsychAiAnalysisContext) -> bool:
    """Nothing to analyze yet — e.g. a report generated before any optional
    extended block (Belbin/АСТУР) was even assigned, on top of a bare-bones
    core result. Callers skip generation entirely in this case rather than
    spending an LLM call on an empty context."""
    return bool(context.blocks)
