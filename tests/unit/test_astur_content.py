"""Public АСТУР content served to the test-taker (PRO-430, PRO-441)."""
import uuid

from app.services.astur.content import build_content
from tests.astur_fixtures import v1_bank

# Enough attempts that a bank-order position surviving every one of them
# cannot be luck: a 4-option item keeps its answer in place 1 time in 4.
RUNS = 200


def _bank_subtest(bank, key: str):
    return next(s for s in bank.subtests if s.key == key)


def _served_subtest(content: dict, key: str) -> dict:
    return next(s for s in content["subtests"] if s["key"] == key)


def _build(bank, run_id: uuid.UUID) -> dict:
    return build_content(bank, bank_version=1, run_id=run_id, locale="ru")


def test_logical_schemas_are_never_served_in_key_order() -> None:
    bank = v1_bank()
    key_orders = [item["concepts"]["ru"] for item in _bank_subtest(bank, "logical_schemas").items]
    # 1/24 per 4-concept item: this many attempts make a plain shuffle's
    # pre-solved item all but certain, so a regression cannot pass by luck.
    for _ in range(300):
        served = _served_subtest(_build(bank, uuid.uuid4()), "logical_schemas")
        for item, key in zip(served["items"], key_orders):
            assert item["concepts"] != key
            assert sorted(item["concepts"]) == sorted(key)


def test_shuffle_does_not_touch_the_cached_bank() -> None:
    bank = v1_bank()
    fields = {"logical_schemas": "concepts", "classification": "words", "awareness": "options", "analogies": "options"}

    def snapshot() -> dict:
        return {
            key: [list(item[field]["ru"]) for item in _bank_subtest(bank, key).items]
            for key, field in fields.items()
        }

    before = snapshot()
    for _ in range(5):
        _build(bank, uuid.uuid4())
    assert snapshot() == before


def test_same_attempt_is_served_the_same_order() -> None:
    bank = v1_bank()
    run_id = uuid.uuid4()
    assert _build(bank, run_id) == _build(bank, run_id)


def test_classification_pair_is_not_always_first_two_words() -> None:
    bank = v1_bank()
    bank_items = _bank_subtest(bank, "classification").items
    seen: dict[str, set[frozenset[int]]] = {item["item_id"]: set() for item in bank_items}
    for _ in range(RUNS):
        served = _served_subtest(_build(bank, uuid.uuid4()), "classification")
        for bank_item, item in zip(bank_items, served["items"]):
            answer = set(bank_item["answer"]["ru"])
            assert sorted(item["words"]) == sorted(bank_item["words"]["ru"])
            seen[item["item_id"]].add(frozenset(i for i, w in enumerate(item["words"]) if w in answer))
    for item_id, positions in seen.items():
        assert positions != {frozenset({0, 1})}, item_id
        assert len(positions) > 1, item_id


def test_single_choice_answer_moves_between_positions() -> None:
    bank = v1_bank()
    keys = ("awareness", "analogies")
    seen: dict[str, set[int]] = {
        item["item_id"]: set() for key in keys for item in _bank_subtest(bank, key).items
    }
    for _ in range(RUNS):
        content = _build(bank, uuid.uuid4())
        for key in keys:
            for bank_item, item in zip(_bank_subtest(bank, key).items, _served_subtest(content, key)["items"]):
                assert sorted(item["options"]) == sorted(bank_item["options"]["ru"])
                seen[item["item_id"]].add(item["options"].index(bank_item["answer"]["ru"]))
    for item_id, positions in seen.items():
        assert len(positions) > 1, f"{item_id}: answer always at {positions}"


def test_unshuffled_subtests_keep_bank_order() -> None:
    bank = v1_bank()
    served = _build(bank, uuid.uuid4())
    for key, field in (("lability", "options"), ("numeric_series", "sequence"), ("generalization", "pair")):
        bank_values = [item[field] for item in _bank_subtest(bank, key).items]
        served_values = [item[field] for item in _served_subtest(served, key)["items"]]
        for bank_value, served_value in zip(bank_values, served_values):
            expected = bank_value["ru"] if isinstance(bank_value, dict) else bank_value
            assert served_value == expected
    # Options А–Г are bound to their images: every attempt sees them alike.
    figures = _served_subtest(served, "geometric_figures")
    for _ in range(20):
        assert _served_subtest(_build(bank, uuid.uuid4()), "geometric_figures") == figures
