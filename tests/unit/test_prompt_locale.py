"""Unit tests for prompt localization directives and glossary (KZ-401)."""
from pathlib import Path
import pytest

from app.prompts._locale import (
    get_direction_name_kk,
    glossary_block,
    language_directive,
    load_direction_glossary,
)
from app.prompts import report_narrative as narrative_prompt
from app.schemas.report_narrative_context import (
    EvidenceItem,
    ReportNarrativeContext,
)


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
