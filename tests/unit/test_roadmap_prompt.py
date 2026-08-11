"""Область 9 §9.3: goal roadmap (app/prompts/roadmap.py) — the "план в одно
предложение" complaint traced back to `ROADMAP_JSON_SCHEMA` never asking the
model for `description` at all (only text/category/priority), even though
`RoadmapTask.description` already exists on the Pydantic model.

Pure prompt-text/schema unit tests — no DB, no LLM, same style as
tests/unit/test_direction_roadmap_prompt.py.
"""
from app.prompts import roadmap as roadmap_prompt


def _task_schema() -> dict:
    return roadmap_prompt.ROADMAP_JSON_SCHEMA["properties"]["milestones"]["items"][
        "properties"
    ]["tasks"]["items"]


def test_task_schema_requires_description():
    task_schema = _task_schema()
    assert "description" in task_schema["required"]
    assert task_schema["properties"]["description"] == {"type": "string"}


def test_task_schema_still_requires_the_original_fields():
    # Область 9 only adds description — text/category/priority must stay.
    task_schema = _task_schema()
    assert set(task_schema["required"]) == {"text", "description", "category", "priority"}


def test_system_prompt_gives_a_qualitative_criterion_not_a_bare_sentence_count():
    # Mirrors direction_roadmap's (a)/(b)/(c) criterion, calibrated lighter —
    # not "write N sentences" but "each sentence must do concrete work".
    system = roadmap_prompt._SYSTEM_PROMPT
    assert "description" in system
    assert "Запрещены общие фразы без конкретики" in system


def test_system_prompt_allows_personality_and_motivation_with_relevance_gating():
    # §9.1/§9.2 data reaches this prompt "for free" via context.model_dump_json,
    # but the model still needs instructional text telling it the fields exist,
    # that they're optional/relevance-gated, and that raw scores/labels are
    # off-limits.
    system = roadmap_prompt._SYSTEM_PROMPT
    assert "personality_notes" in system
    assert "motivation_top" in system or "motivation_highlights" in system
    assert "Никогда не цитируй числа" in system
    assert "не наклеивай ярлык" in system
