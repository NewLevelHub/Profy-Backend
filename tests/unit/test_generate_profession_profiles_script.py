import pytest

from app.services import llm_client
from scripts.generate_profession_profiles import (
    draft_profiles,
    generate_profile,
    select_leaves,
)

NODES = [
    {"slug": "medicine", "name": "Медицина", "parent_slug": None, "is_leaf": False},
    {"slug": "surgeon", "name": "Хирург", "parent_slug": "medicine", "is_leaf": True},
    {"slug": "dentist", "name": "Стоматолог", "parent_slug": "medicine", "is_leaf": True},
]


def test_select_leaves_skips_non_leaf_nodes_and_resolves_category():
    leaves = select_leaves(NODES)
    assert {leaf["slug"] for leaf in leaves} == {"surgeon", "dentist"}
    assert all(leaf["category"] == "Медицина" for leaf in leaves)


def test_select_leaves_falls_back_to_raw_parent_slug_when_parent_missing():
    nodes = [{"slug": "surgeon", "name": "Хирург", "parent_slug": "ghost", "is_leaf": True}]
    leaves = select_leaves(nodes)
    assert leaves[0]["category"] == "ghost"


async def test_generate_profile_returns_one_profile_per_leaf(monkeypatch):
    """AC1: one profile per leaf, values within -2..2."""

    async def fake_complete_json(messages, schema, schema_name, **kwargs):
        assert schema_name == "akinator_profile"
        return {"axes": [{"code": "People", "value": 1}, {"code": "Care", "value": 2}]}

    monkeypatch.setattr(llm_client, "complete_json", fake_complete_json)

    leaf = {"slug": "surgeon", "name": "Хирург", "category": "Медицина"}
    axes, problems = await generate_profile(leaf)

    assert axes == {"People": 1, "Care": 2}
    assert all(-2 <= v <= 2 for v in axes.values())
    assert problems == []


async def test_generate_profile_retries_then_drops_unknown_axis_codes(monkeypatch):
    """AC2: unknown axis codes never reach the output, even after retries are exhausted."""
    calls = []

    async def fake_complete_json(messages, schema, schema_name, **kwargs):
        calls.append(messages)
        return {"axes": [{"code": "People", "value": 1}, {"code": "B_analyze", "value": 2}]}

    monkeypatch.setattr(llm_client, "complete_json", fake_complete_json)

    leaf = {"slug": "surgeon", "name": "Хирург", "category": None}
    axes, problems = await generate_profile(leaf)

    assert axes == {"People": 1}
    assert "B_analyze" not in axes
    assert len(calls) == 3  # 1 initial attempt + MAX_AXIS_RETRIES(2) re-asks
    assert any("B_analyze" in p for p in problems)


async def test_generate_profile_recovers_after_one_retry(monkeypatch):
    responses = [
        {"axes": [{"code": "B_analyze", "value": 2}]},
        {"axes": [{"code": "Obj", "value": 2}]},
    ]

    async def fake_complete_json(messages, schema, schema_name, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(llm_client, "complete_json", fake_complete_json)

    leaf = {"slug": "surgeon", "name": "Хирург", "category": None}
    axes, problems = await generate_profile(leaf)

    assert axes == {"Obj": 2}
    assert problems == []


async def test_draft_profiles_skips_a_leaf_whose_llm_call_fails(monkeypatch):
    async def raising_complete_json(*args, **kwargs):
        raise llm_client.LLMError("boom")

    monkeypatch.setattr(llm_client, "complete_json", raising_complete_json)

    profiles, problems = await draft_profiles(NODES)

    assert profiles == []
    assert len(problems) == 2  # one per leaf (surgeon, dentist)
    assert any("LLM call failed" in p for p in problems)


async def test_draft_profiles_ignores_non_leaf_nodes(monkeypatch):
    async def fake_complete_json(messages, schema, schema_name, **kwargs):
        return {"axes": [{"code": "People", "value": 1}]}

    monkeypatch.setattr(llm_client, "complete_json", fake_complete_json)

    profiles, problems = await draft_profiles(NODES)

    assert {p["slug"] for p in profiles} == {"surgeon", "dentist"}
    assert problems == []
