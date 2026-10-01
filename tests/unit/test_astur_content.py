"""Public АСТУР content served to the test-taker (PRO-430)."""
import random
import uuid

from app.services.astur.bank import parse_bank
from app.services.astur.content import build_content
from tests.astur_fixtures import v1_bank


def test_content_uses_versioned_presentation_order() -> None:
    document = v1_bank().model_dump()
    document["presentation_order"] = [
        "awareness", "analogies", "lability", "geometric_figures",
        "classification", "generalization", "logical_schemas", "numeric_series",
    ]

    content = build_content(parse_bank(document), bank_version=2, run_id=uuid.uuid4(), locale="ru")

    assert [subtest["key"] for subtest in content["subtests"]] == document["presentation_order"]
    assert content["subtests"][3]["number"] == 8


def _chain_subtest(content: dict) -> dict:
    return next(s for s in content["subtests"] if s["key"] == "logical_schemas")


def test_logical_schemas_are_never_served_in_key_order() -> None:
    bank = v1_bank()
    key_orders = [
        item["concepts"]["ru"]
        for item in next(s for s in bank.subtests if s.key == "logical_schemas").items
    ]
    random.seed(0)
    # 1/24 per 4-concept item: 300 builds make a plain shuffle's pre-solved
    # item all but certain, so a regression cannot pass by luck.
    for _ in range(300):
        served = _chain_subtest(build_content(bank, bank_version=1, run_id=uuid.uuid4(), locale="ru"))
        for item, key in zip(served["items"], key_orders):
            assert item["concepts"] != key
            assert sorted(item["concepts"]) == sorted(key)


def test_shuffle_does_not_touch_the_cached_bank() -> None:
    bank = v1_bank()
    before = [
        list(item["concepts"]["ru"])
        for item in next(s for s in bank.subtests if s.key == "logical_schemas").items
    ]
    build_content(bank, bank_version=1, run_id=uuid.uuid4(), locale="ru")
    after = [
        item["concepts"]["ru"]
        for item in next(s for s in bank.subtests if s.key == "logical_schemas").items
    ]
    assert after == before
