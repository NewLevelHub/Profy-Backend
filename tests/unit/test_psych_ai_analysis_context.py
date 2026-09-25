"""PRO-338+ — psych_ai_analysis_context.py: builds the raw-data bundle the
AI-analysis prompt reads from. Pure functions, no DB/LLM."""
import uuid
from datetime import datetime, timezone

from app.prompts.psych_ai_analysis import build_messages
from app.schemas.new_tests import IntelligenceSection, NewTestsSections, TeamRoleSection, TemperamentSection
from app.schemas.result_v2 import RiasecResultResponse, StudentCareer, StudentInterestMapItem, StudentPersonalityNote
from app.services.bigfive_content import personality_labels
from app.services.astur.scoring import score_attempt
from app.services.astur.scoring_rules import get_rules
from app.services.psych_ai_analysis_context import build_context, fingerprint, has_any_data
from tests.astur_fixtures import attempt_input, content_answers, v1_bank

_NOW = datetime.now(timezone.utc)
_RIASEC_CODES = ["R", "I", "A", "S", "E", "C"]


def _personality_notes() -> list[StudentPersonalityNote]:
    return [
        StudentPersonalityNote(trait=trait, label=label, description="Короткое описание")
        for trait, label in personality_labels().items()
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


# ── PRO-427: АСТУР block + age/grade + cache fingerprint ────────────────────


def _intelligence_section(**overrides) -> IntelligenceSection:
    bank = v1_bank()
    snapshot = score_attempt(bank, attempt_input(bank, content_answers(bank)), get_rules("2"))
    fields = dict(run_id=uuid.uuid4(), retake_in_progress=False, **snapshot.model_dump(exclude={"item_scores"}))
    fields.update(overrides)
    return IntelligenceSection(**fields)


def test_intelligence_block_is_labelled_as_study_tasks_without_norm_fields() -> None:
    context = build_context(
        _bare_report(), NewTestsSections(intelligence=_intelligence_section()), student_name="Аружан"
    )
    block = next(b for b in context.blocks if b.key == "intelligence")
    assert block.label == "Когнитивные навыки (учебные задания)"
    assert "spn_group" not in block.facts
    assert "lability_fatigue_signal" not in block.facts
    assert {"subtests", "overall_percent", "subject_profile", "protocol_quality"} <= block.facts.keys()
    assert block.facts["age_at_completion"] == 16
    assert "run_id" not in block.facts


def test_student_age_and_grade_reach_the_context_and_the_prompt() -> None:
    context = build_context(
        _bare_report(), NewTestsSections(), student_name="Аружан", student_age=14, student_grade=8
    )
    system = build_messages(context)[0]["content"]
    assert "Возраст ученика: 14." in system
    assert "Класс: 8." in system
    assert "не IQ" in system

    unknown = build_messages(build_context(_bare_report(), NewTestsSections(), student_name="Аружан"))[0]["content"]
    assert "Возраст ученика неизвестен." in unknown


def test_fingerprint_changes_with_a_new_attempt_or_age_but_not_otherwise() -> None:
    report = _bare_report()
    section = _intelligence_section()
    base = fingerprint(build_context(report, NewTestsSections(intelligence=section), student_name="А", student_age=15))
    same = fingerprint(build_context(report, NewTestsSections(intelligence=section), student_name="А", student_age=15))
    older = fingerprint(build_context(report, NewTestsSections(intelligence=section), student_name="А", student_age=16))
    new_attempt = fingerprint(build_context(
        report, NewTestsSections(intelligence=_intelligence_section(overall_percent=42.0)),
        student_name="А", student_age=15,
    ))
    assert base == same
    assert base != older
    assert base != new_attempt
