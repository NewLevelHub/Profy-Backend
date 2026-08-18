"""Deterministic keyword matching for the roadmap's "Дополнительный источник"
block — see app/data/resource_catalog.py. No LLM involved, so this is plain
unit-testable logic."""
from app.data import resource_catalog


def test_architect_matches_creative_design():
    category = resource_catalog.match_category(
        "Архитектор", "Архитектурный рисунок и черчение", "черчение изобразительное искусство",
    )
    assert category == "creative_design"


def test_backend_developer_matches_tech():
    category = resource_catalog.match_category(
        "Backend-разработчик", "Python, алгоритмы, базы данных", "информатика математика",
    )
    assert category == "tech"


def test_lawyer_matches_law():
    category = resource_catalog.match_category(
        "Юрист", "анализ законодательства", "право обществознание",
    )
    assert category == "law"


def test_no_keyword_hits_returns_none():
    assert resource_catalog.match_category("Зюзюка", "", "") is None


def test_empty_input_returns_none():
    assert resource_catalog.match_category("", "", "") is None


def test_resources_for_none_category_is_empty():
    assert resource_catalog.resources_for_category(None) == []


def test_resources_for_category_capped_at_five():
    for category, items in resource_catalog.RESOURCE_CATALOG.items():
        assert len(resource_catalog.resources_for_category(category)) <= 5
        assert len(items) <= 5


def test_catalog_entries_have_required_fields_and_no_duplicate_urls():
    seen_urls = set()
    for items in resource_catalog.RESOURCE_CATALOG.values():
        for item in items:
            assert item["title"]
            assert item["kind"]
            assert item["url"].startswith("https://")
            assert item["url"] not in seen_urls, f"duplicate url: {item['url']}"
            seen_urls.add(item["url"])


def test_every_catalog_category_has_keywords():
    assert set(resource_catalog.RESOURCE_CATALOG.keys()) == set(resource_catalog.CATEGORY_KEYWORDS.keys())
