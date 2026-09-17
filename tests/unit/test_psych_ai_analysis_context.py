"""PRO-338+ — psych_ai_analysis_context.py: builds the raw-data bundle the
AI-analysis prompt reads from. Pure functions, no DB/LLM."""
import uuid
from datetime import datetime, timezone

from app.schemas.new_tests import NewTestsSections, TeamRoleSection, TemperamentSection
from app.schemas.result_v2 import RiasecResultResponse, StudentCareer, StudentInterestMapItem, StudentPersonalityNote
from app.services.bigfive_content import PERSONALITY_LABELS
from app.services.psych_ai_analysis_context import build_context, has_any_data

_NOW = datetime.now(timezone.utc)
_RIASEC_CODES = ["R", "I", "A", "S", "E", "C"]


def _personality_notes() -> list[StudentPersonalityNote]:
    return [
        StudentPersonalityNote(trait=trait, label=label, description="Короткое описание")
        for trait, label in PERSONALITY_LABELS.items()
    ]


def _bare_report(**overrides) -> RiasecResultResponse:
    kwargs = dict(
        assessment_id=uuid.uuid4(),
        summary="Резюме.",
        strength_cards=[],
        interest_map=[StudentInterestMapItem(code=c, sphere=c, level="medium") for c in _RIASEC_CODES],
        thinking_style_notes=[],
        personality_notes=_personality_notes(),
        motivation_highlights=[],
        careers=[],
        is_flat_profile=False,
        created_at=_NOW,
    )
    kwargs.update(overrides)
    return RiasecResultResponse(**kwargs)


def test_empty_new_tests_and_bare_report_still_yields_interests_and_personality_blocks() -> None:
    report = _bare_report()
    context = build_context(report, NewTestsSections(), student_name="Аружан")

    keys = {b.key for b in context.blocks}
    # interest_map/personality_notes are always non-empty on a real report
    # (schema-enforced cardinality), so they always produce a block.
    assert "interests" in keys
    assert "personality" in keys
    assert "temperament" not in keys
    assert "team_role" not in keys
    assert context.careers == []


def test_new_tests_sections_only_added_when_present() -> None:
    report = _bare_report()
    new_tests = NewTestsSections(
        temperament=TemperamentSection(extraversion_raw=15, neuroticism_raw=10),
        team_role=TeamRoleSection(dominant_role="coordinator"),
    )
    context = build_context(report, new_tests, student_name="Аружан")

    keys = {b.key for b in context.blocks}
    assert "temperament" in keys
    assert "team_role" in keys
    assert "aspiration_level" not in keys
    assert "intelligence" not in keys


def test_temperament_block_facts_exclude_none_fields() -> None:
    report = _bare_report()
    new_tests = NewTestsSections(temperament=TemperamentSection(extraversion_raw=15, neuroticism_raw=10))
    context = build_context(report, new_tests, student_name="Аружан")

    temperament_block = next(b for b in context.blocks if b.key == "temperament")
    assert temperament_block.facts == {"extraversion_raw": 15, "neuroticism_raw": 10}
    assert temperament_block.label == "Темперамент (Айзенк)"


def test_careers_are_carried_through_as_slug_name_why() -> None:
    report = _bare_report(careers=[
        StudentCareer(slug="swe", name="Разработчик", rank=1, tier="strong", why="Совпало с интересами", try_now="Попробуй"),
    ])
    context = build_context(report, NewTestsSections(), student_name="Аружан")

    assert len(context.careers) == 1
    assert context.careers[0].slug == "swe"
    assert context.careers[0].name == "Разработчик"
    assert context.careers[0].why == "Совпало с интересами"


def test_has_any_data_true_with_at_least_one_block() -> None:
    report = _bare_report()
    context = build_context(report, NewTestsSections(), student_name="Т")
    assert has_any_data(context) is True
