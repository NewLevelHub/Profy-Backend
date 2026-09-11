"""app/prompts/report_narrative.py — pure prompt-text/schema unit tests, no
DB, no LLM. Same style as tests/unit/test_roadmap_prompt.py.

Structured Outputs (strict mode) forbids minItems/maxItems, so exact
cardinality (8 MI / 6 RIASEC interests, junior's empty career_narrative)
can't be enforced by the JSON schema itself — this file checks the schema
shape and that the system prompt actually spells out those rules in text,
since app.services.report_narrative_validator is what enforces them for real.
"""
from app.models.profile import AgeGroup
from app.prompts import report_narrative as prompt
from app.schemas.report_narrative_context import EvidenceItem, ReportNarrativeContext
from app.services.mi_content import mi_labels
from app.services.riasec_content import riasec_labels


def _junior_context() -> ReportNarrativeContext:
    return ReportNarrativeContext(
        age_group=AgeGroup.junior.value,
        interest_instrument="mi",
        evidence=[EvidenceItem(source_id="mi:logical", source_type="mi_category", text="Логика и счёт")],
    )


def _senior_context() -> ReportNarrativeContext:
    return ReportNarrativeContext(
        age_group=AgeGroup.senior.value,
        interest_instrument="riasec",
        evidence=[EvidenceItem(source_id="riasec:R", source_type="riasec_category", text="Реалистичный")],
    )


def test_schema_top_level_requires_all_seven_sections():
    assert set(prompt.NARRATIVE_JSON_SCHEMA["required"]) == {
        "summary", "strength_cards", "interests", "thinking_style_notes",
        "motivation_narrative", "career_narrative", "final_analysis",
    }
    assert prompt.NARRATIVE_JSON_SCHEMA["additionalProperties"] is False


def test_card_schema_requires_evidence_ids():
    strength_item_schema = prompt.NARRATIVE_JSON_SCHEMA["properties"]["strength_cards"]["items"]
    assert set(strength_item_schema["required"]) == {"title", "description", "evidence_ids"}
    assert strength_item_schema["properties"]["evidence_ids"]["type"] == "array"


def test_interest_schema_has_category_and_strong_steady_tier():
    interest_item_schema = prompt.NARRATIVE_JSON_SCHEMA["properties"]["interests"]["items"]
    assert set(interest_item_schema["required"]) == {"category", "tier", "title", "description"}
    assert interest_item_schema["properties"]["tier"]["enum"] == ["strong", "steady"]


def test_motivation_narrative_schema_is_a_single_card_not_a_list():
    motivation_schema = prompt.NARRATIVE_JSON_SCHEMA["properties"]["motivation_narrative"]
    assert motivation_schema["type"] == "object"
    assert set(motivation_schema["required"]) == {"title", "description", "evidence_ids"}


def test_build_messages_returns_system_and_user_roles():
    messages = prompt.build_messages(_senior_context())
    assert [m["role"] for m in messages] == ["system", "user"]
    assert messages[1]["content"]


def test_junior_system_prompt_forbids_career_narrative_and_lists_all_eight_mi_categories():
    system = prompt._system_prompt(_junior_context())
    assert "career_narrative обязан быть пустым списком" in system
    assert len(mi_labels()) == 8
    for key, label in mi_labels().items():
        assert f"{key} ({label})" in system


def test_senior_system_prompt_allows_limited_career_narrative_and_lists_six_riasec_categories():
    system = prompt._system_prompt(_senior_context())
    assert "не больше 3 карточек" in system
    assert len(riasec_labels()) == 6
    for key, label in riasec_labels().items():
        assert f"{key} ({label})" in system


def test_system_prompt_embeds_the_full_banned_phrase_list():
    system = prompt._system_prompt(_senior_context())
    for phrase in ["ты гуманитарий", "слабая сторона", "ты точно поступишь", "если не начнёшь сейчас"]:
        assert phrase in system


def test_system_prompt_requires_evidence_backed_claims_and_bans_numbers():
    system = prompt._system_prompt(_senior_context())
    assert "source_id" in system
    assert "Никогда не цитируй числа" in system


def test_system_prompt_forbids_thinking_style_evidence_in_strength_cards():
    system = prompt._system_prompt(_senior_context())
    assert 'НЕ используй здесь evidence с source_type "thinking_style"' in system


def test_system_prompt_embeds_the_evidence_catalog_as_json():
    context = _senior_context()
    system = prompt._system_prompt(context)
    assert "riasec:R" in system
