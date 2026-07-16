import pytest

from app.services import llm_client
from scripts.generate_questions import check_format_rule, generate_batch, generate_question


def test_check_format_rule_accepts_matching_kind():
    # People is family A -> always direct, any depth.
    assert check_format_rule("People", depth=0, kind="direct") is None


def test_check_format_rule_flags_mismatch():
    # Focus is family D -> always situational; asking for direct is a violation.
    problem = check_format_rule("Focus", depth=0, kind="direct")
    assert problem is not None
    assert "Focus" in problem
    assert "situational" in problem


def test_check_format_rule_respects_depth_dependent_families():
    # Inv is family B -> direct while shallow, situational from depth 2.
    assert check_format_rule("Inv", depth=1, kind="direct") is None
    assert check_format_rule("Inv", depth=2, kind="direct") is not None
    assert check_format_rule("Inv", depth=2, kind="situational") is None


async def test_generate_question_returns_valid_node_for_a_test_prompt(monkeypatch):
    """AC1: generated questions pass schema + AXIS_CODES validation."""

    async def fake_complete_json(messages, schema, schema_name, **kwargs):
        assert schema_name == "akinator_question"
        return {
            "text": "Что тебе интереснее всего?",
            "text_junior": None,
            "options": [
                {
                    "text": "быть среди людей, общаться, помогать",
                    "axis_weights": [{"code": "People", "value": 2}],
                },
                {
                    "text": "разбираться, как устроены вещи",
                    "axis_weights": [{"code": "Phys", "value": 1}, {"code": "Data", "value": 1}],
                },
            ],
        }

    monkeypatch.setattr(llm_client, "complete_json", fake_complete_json)

    node, problems = await generate_question(
        "People", depth=0, kind="direct", age_variant="both", resolves_pair=None, order=0
    )

    assert problems == []
    assert node is not None
    assert node["options"][0]["axis_weights"] == {"People": 2}
    assert node["kind"] == "direct"


async def test_generate_question_flags_format_rule_mismatch_but_still_drafts(monkeypatch):
    async def fake_complete_json(messages, schema, schema_name, **kwargs):
        return {
            "text": "Стуб",
            "text_junior": None,
            "options": [{"text": "вариант", "axis_weights": [{"code": "Focus", "value": 2}]}],
        }

    monkeypatch.setattr(llm_client, "complete_json", fake_complete_json)

    # Focus is always situational; requesting "direct" is a rule violation.
    node, problems = await generate_question(
        "Focus", depth=0, kind="direct", age_variant="both", resolves_pair=None, order=0
    )

    assert node is not None  # still drafted, not blocked
    assert any("format rule mismatch" in p for p in problems)


async def test_generate_question_flags_missing_target_axis_coverage(monkeypatch):
    async def fake_complete_json(messages, schema, schema_name, **kwargs):
        return {
            "text": "Стуб",
            "text_junior": None,
            "options": [{"text": "вариант", "axis_weights": [{"code": "Data", "value": 1}]}],
        }

    monkeypatch.setattr(llm_client, "complete_json", fake_complete_json)

    node, problems = await generate_question(
        "People", depth=0, kind="direct", age_variant="both", resolves_pair=None, order=0
    )

    assert node is not None
    assert any("not covered" in p for p in problems)


async def test_generate_batch_rejects_unknown_axis_before_any_llm_call(monkeypatch):
    async def should_not_be_called(*args, **kwargs):
        raise AssertionError("LLM must not be called for an unknown axis")

    monkeypatch.setattr(llm_client, "complete_json", should_not_be_called)

    nodes, problems = await generate_batch(
        "NotAnAxis", depth=0, kind="direct", age_variant="both", resolves_pair=None, count=3
    )

    assert nodes == []
    assert any("unknown axis code" in p for p in problems)


async def test_generate_batch_surfaces_llm_error_per_item(monkeypatch):
    async def raising_complete_json(*args, **kwargs):
        raise llm_client.LLMError("boom")

    monkeypatch.setattr(llm_client, "complete_json", raising_complete_json)

    nodes, problems = await generate_batch(
        "People", depth=0, kind="direct", age_variant="both", resolves_pair=None, count=2
    )

    assert nodes == []
    assert len(problems) == 2
    assert all("LLM call failed" in p for p in problems)
