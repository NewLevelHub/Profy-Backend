"""Unit tests for prompt localization directives and glossary (KZ-401)."""
from pathlib import Path
import pytest

from app.models.direction import Direction
from app.prompts._locale import (
    get_direction_name_kk,
    glossary_block,
    language_directive,
    load_direction_glossary,
)
from app.prompts import (
    direction_inquiry as inquiry_prompt,
    direction_roadmap as direction_prompt,
    report_narrative as narrative_prompt,
    roadmap as roadmap_prompt,
)
from app.schemas.report_narrative_context import (
    EvidenceItem,
    ReportNarrativeContext,
)
from app.schemas.student_context import ContextCareer, StudentContext


def _sample_evidence() -> list[EvidenceItem]:
    return [
        EvidenceItem(
            source_id="think_1",
            source_type="thinking_style",
            text="Системное аналитическое мышление",
        ),
        EvidenceItem(
            source_id="pers_1",
            source_type="personality",
            text="Умеет структурировать информацию",
        ),
    ]


def _sample_context(locale: str = "ru") -> StudentContext:
    return StudentContext(
        name="Алихан",
        age=16,
        age_group="senior",
        grade=10,
        city="Алматы",
        country="Казахстан",
        language="Казахский",
        locale=locale,
        subjects_liked=["Информатика", "Физика"],
        subjects_disliked=["Биология"],
        subjects_easy=["Математика"],
        subjects_hard=["Химия"],
        artifacts=[],
        goal="explore",
        summary="Сильный аналитический профиль",
        profile={"R": 80.0, "I": 90.0, "A": 30.0, "S": 40.0, "E": 50.0, "C": 70.0},
        code=["I", "R", "C"],
        strengths=["Логика", "Анализ"],
        weaknesses=["Публичные выступления"],
        personality_profile={"openness": 70.0},
        personality_notes={"openness": "любит новые задачи"},
        thinking_style={"analytical": 85.0},
        motivation_top=["Мастерство"],
        motivation_highlights=["Стремится к глубокому пониманию"],
        careers=[
            ContextCareer(
                slug="software_engineer",
                name="Инженер-программист",
                holland_code="IRC",
                match_score=95,
            )
        ],
    )


def _sample_direction() -> Direction:
    return Direction(
        slug="software_engineer",
        name="Инженер-программист",
        holland_code="IRC",
        description="Разработка программного обеспечения",
        professions=["Разработчик ПО", "Архитектор систем"],
        skills_needed=["Python", "Алгоритмы"],
        subjects_to_develop=["Информатика", "Математика"],
    )


# ─── 1. Directive & Glossary Helper Tests ────────────────────────────────────


def test_language_directive_ru():
    assert language_directive("ru") == "Язык ответа — русский."


def test_language_directive_kk():
    assert language_directive("kk") == (
        "Жауапты тек қазақ тілінде бер. "
        "Орыс немесе ағылшын сөздерін қолданба (кірме терминдерден басқа)."
    )


def test_language_directive_fallback():
    assert language_directive("en") == "Язык ответа — русский."
    assert language_directive("") == "Язык ответа — русский."


def test_glossary_block_ru_is_empty():
    assert glossary_block("ru") == ""
    assert glossary_block("ru", direction_slug="software_engineer") == ""


def test_glossary_block_kk_contains_rules():
    kk_block = glossary_block("kk")
    assert "ГЛОССАРИЙ ЖӘНЕ АТАУЛАР ЕРЕЖЕСІ" in kk_block
    assert "Nazarbayev University" in kk_block
    assert "ҰБТ" in kk_block
    assert "бейіндік пәндер" in kk_block
    assert "шектік балл" in kk_block
    assert "Data Engineer" in kk_block
    assert "Mobile-әзірлеуші" in kk_block
    assert "QA-инженер (тестілеуші)" in kk_block


def test_direction_glossary_loaded():
    glossary = load_direction_glossary()
    assert len(glossary) >= 100
    assert "slug" in next(iter(glossary.values()))


def test_get_direction_name_kk():
    # If slug is in glossary, it returns Kazakh name
    glossary = load_direction_glossary()
    if glossary:
        first_slug = next(iter(glossary.keys()))
        name_kk = get_direction_name_kk(first_slug)
        assert name_kk is not None
        assert isinstance(name_kk, str)


# ─── 2. Audit: No Hardcoded Russian Literals in Prompts ──────────────────────


def test_no_hardcoded_russian_literals_in_prompts():
    prompts_dir = Path(__file__).resolve().parent.parent.parent / "app" / "prompts"
    prompt_files = [
        "report_narrative.py",
        "roadmap.py",
        "direction_roadmap.py",
        "direction_inquiry.py",
    ]
    for filename in prompt_files:
        filepath = prompts_dir / filename
        content = filepath.read_text(encoding="utf-8")
        # Ensure no hardcoded literals remain
        assert "язык ответа — русский" not in content.lower(), f"Literal found in {filename}"
        assert "язык — русский" not in content.lower(), f"Literal found in {filename}"


# ─── 3. Byte Parity / Backward Compatibility for Russian ─────────────────────


def test_report_narrative_ru_backward_compatibility():
    context = ReportNarrativeContext(
        age_group="senior",
        interest_instrument="riasec",
        categories=["R", "I"],
        personality_notes={},
        thinking_style_notes={},
        motivation_notes={},
        evidence=_sample_evidence(),
    )
    messages = narrative_prompt.build_messages(context, language="ru")
    system_content = messages[0]["content"]
    assert "Язык ответа — русский." in system_content
    assert "ГЛОССАРИЙ" not in system_content


def test_roadmap_ru_backward_compatibility():
    context = _sample_context(locale="ru")
    messages = roadmap_prompt.build_messages(context, locale="ru")
    system_content = messages[0]["content"]
    assert "Язык ответа — русский." in system_content
    assert "ГЛОССАРИЙ" not in system_content
    assert system_content == roadmap_prompt._SYSTEM_PROMPT


def test_direction_roadmap_ru_backward_compatibility():
    context = _sample_context(locale="ru")
    direction = _sample_direction()
    messages = direction_prompt.build_messages(context, direction, locale="ru")
    system_content = messages[0]["content"]
    assert "Язык ответа — русский." in system_content
    assert "ГЛОССАРИЙ" not in system_content


def test_direction_inquiry_ru_backward_compatibility():
    context = _sample_context(locale="ru")
    direction = _sample_direction()
    q_messages = inquiry_prompt.build_questions_messages(context, direction, locale="ru")
    assert "Язык ответа — русский." in q_messages[0]["content"]
    assert "ГЛОССАРИЙ" not in q_messages[0]["content"]
    assert q_messages[0]["content"] == inquiry_prompt._QUESTIONS_SYSTEM

    v_messages = inquiry_prompt.build_verdict_messages(context, direction, [], locale="ru")
    assert "Язык ответа — русский." in v_messages[0]["content"]
    assert "ГЛОССАРИЙ" not in v_messages[0]["content"]
    assert v_messages[0]["content"] == inquiry_prompt._VERDICT_SYSTEM


# ─── 4. Kazakh Prompt Generation (KZ-401 Acceptance Criteria) ────────────────


def test_report_narrative_kk_generation():
    context = ReportNarrativeContext(
        age_group="senior",
        interest_instrument="riasec",
        categories=["R", "I"],
        personality_notes={},
        thinking_style_notes={},
        motivation_notes={},
        evidence=_sample_evidence(),
    )
    messages = narrative_prompt.build_messages(context, language="kk")
    system_content = messages[0]["content"]
    user_content = messages[1]["content"]

    kk_directive = language_directive("kk")
    assert kk_directive in system_content
    assert kk_directive in user_content
    assert "ГЛОССАРИЙ ЖӘНЕ АТАУЛАР ЕРЕЖЕСІ" in system_content
    assert "Язык ответа — русский" not in system_content


def test_roadmap_kk_generation():
    context = _sample_context(locale="kk")
    messages = roadmap_prompt.build_messages(context)  # Uses context.locale
    system_content = messages[0]["content"]

    kk_directive = language_directive("kk")
    assert kk_directive in system_content
    assert "ГЛОССАРИЙ ЖӘНЕ АТАУЛАР ЕРЕЖЕСІ" in system_content
    assert "Язык ответа — русский" not in system_content


def test_roadmap_track_kk_generation():
    context = _sample_context(locale="kk")
    messages = roadmap_prompt.build_track_messages(
        context, "Робототехника", "Подходит по силе", "Даёт старт"
    )
    system_content = messages[0]["content"]

    kk_directive = language_directive("kk")
    assert kk_directive in system_content
    assert "ГЛОССАРИЙ ЖӘНЕ АТАУЛАР ЕРЕЖЕСІ" in system_content


def test_direction_roadmap_kk_generation():
    context = _sample_context(locale="kk")
    direction = _sample_direction()
    messages = direction_prompt.build_messages(context, direction)  # Uses context.locale
    system_content = messages[0]["content"]

    kk_directive = language_directive("kk")
    assert kk_directive in system_content
    assert "ГЛОССАРИЙ ЖӘНЕ АТАУЛАР ЕРЕЖЕСІ" in system_content
    assert "Язык ответа — русский" not in system_content


def test_direction_inquiry_kk_generation():
    context = _sample_context(locale="kk")
    direction = _sample_direction()

    q_messages = inquiry_prompt.build_questions_messages(context, direction)
    assert language_directive("kk") in q_messages[0]["content"]
    assert "ГЛОССАРИЙ ЖӘНЕ АТАУЛАР ЕРЕЖЕСІ" in q_messages[0]["content"]

    v_messages = inquiry_prompt.build_verdict_messages(context, direction, [])
    assert language_directive("kk") in v_messages[0]["content"]
    assert "ГЛОССАРИЙ ЖӘНЕ АТАУЛАР ЕРЕЖЕСІ" in v_messages[0]["content"]
