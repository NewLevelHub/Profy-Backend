import pytest

from app.services import llm_client
from scripts.generate_taxonomy import propose_taxonomy, validate_nodes


def test_validate_nodes_accepts_clean_batch():
    nodes = [
        {"slug": "medicine", "name": "Медицина", "parent_slug": None, "is_leaf": False},
        {"slug": "surgeon", "name": "Хирург", "parent_slug": "medicine", "is_leaf": True},
    ]
    assert validate_nodes(nodes, existing_slugs=set()) == []


def test_validate_nodes_rejects_slug_already_in_catalog():
    nodes = [{"slug": "teacher", "name": "Учитель", "parent_slug": None, "is_leaf": True}]
    problems = validate_nodes(nodes, existing_slugs={"teacher"})
    assert any("already exists" in p for p in problems)


def test_validate_nodes_rejects_duplicate_slug_within_batch():
    nodes = [
        {"slug": "surgeon", "name": "Хирург", "parent_slug": None, "is_leaf": True},
        {"slug": "surgeon", "name": "Хирург 2", "parent_slug": None, "is_leaf": True},
    ]
    problems = validate_nodes(nodes, existing_slugs=set())
    assert any("duplicated" in p for p in problems)


def test_validate_nodes_rejects_category_with_no_children_in_batch():
    nodes = [
        {"slug": "sculpture", "name": "Скульптура", "parent_slug": "visual-arts", "is_leaf": False},
        {"slug": "painter", "name": "Художник", "parent_slug": "visual-arts", "is_leaf": True},
    ]
    problems = validate_nodes(nodes, existing_slugs={"visual-arts"})
    assert any("dead end" in p and "sculpture" in p for p in problems)


def test_validate_nodes_rejects_unknown_parent():
    nodes = [{"slug": "surgeon", "name": "Хирург", "parent_slug": "ghost-parent", "is_leaf": True}]
    problems = validate_nodes(nodes, existing_slugs=set())
    assert any("unknown parent_slug" in p for p in problems)


async def test_propose_taxonomy_returns_valid_nodes_for_a_test_prompt(monkeypatch):
    """AC1: a run on a test prompt yields valid JSON per schema. Mocks the LLM
    call (no network/API key needed) so this is deterministic and repeatable."""

    async def fake_complete_json(messages, schema, schema_name, **kwargs):
        assert schema_name == "akinator_taxonomy"
        return {
            "nodes": [
                {"slug": "medicine", "name": "Медицина", "parent_slug": None, "is_leaf": False},
                {"slug": "surgeon", "name": "Хирург", "parent_slug": "medicine", "is_leaf": True},
            ]
        }

    monkeypatch.setattr(llm_client, "complete_json", fake_complete_json)

    nodes, problems = await propose_taxonomy(
        existing_slugs=["teacher"], focus_area="медицина", count=2
    )

    assert problems == []
    assert len(nodes) == 2
    assert {n["slug"] for n in nodes} == {"medicine", "surgeon"}
    assert all({"slug", "name", "parent_slug", "is_leaf"} <= set(n) for n in nodes)


async def test_propose_taxonomy_surfaces_llm_error(monkeypatch):
    async def raising_complete_json(*args, **kwargs):
        raise llm_client.LLMError("boom")

    monkeypatch.setattr(llm_client, "complete_json", raising_complete_json)

    with pytest.raises(llm_client.LLMError):
        await propose_taxonomy(existing_slugs=[], focus_area="", count=1)
