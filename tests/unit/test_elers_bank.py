"""PRO-338 Ф1.7 — content integrity for elers_bank.py's key. No DB
involved, mirrors test_eysenck_bank.py's convention."""
from scripts.elers_bank import QUESTIONS


def test_has_exactly_41_items() -> None:
    assert len(QUESTIONS) == 41


def test_orders_are_unique_and_contiguous_from_470() -> None:
    orders = [q["order"] for q in QUESTIONS]
    assert orders == list(range(470, 511))


def test_every_item_has_a_keyed_direction() -> None:
    for q in QUESTIONS:
        assert q["keyed"] in {"yes", "no", "buffer"}


def test_key_counts_match_the_source_audit() -> None:
    by_keyed: dict[str, list[dict]] = {"yes": [], "no": [], "buffer": []}
    for q in QUESTIONS:
        by_keyed[q["keyed"]].append(q)

    assert len(by_keyed["yes"]) == 23
    assert len(by_keyed["no"]) == 9
    assert len(by_keyed["buffer"]) == 9


def test_specific_items_match_the_source_key_verbatim() -> None:
    """A handful of individually-verifiable anchors against
    docs/psych/new-tests-content-sources.md's key, not exhaustive — the
    count-based test above already proves the aggregate shape."""
    by_order = {q["order"]: q for q in QUESTIONS}

    # Item 1 -> order 470 -> buffer (not counted)
    assert by_order[470]["keyed"] == "buffer"
    # Item 2 -> order 471 -> "yes" (first Да-keyed item)
    assert by_order[471]["keyed"] == "yes"
    # Item 6 -> order 475 -> "no" (first Нет-keyed item)
    assert by_order[475]["keyed"] == "no"
    # Item 41 -> order 510 -> "yes" (the item whose canonical existence
    # this ticket's own audit resolved — must be scored, not dropped)
    assert by_order[510]["keyed"] == "yes"
    assert by_order[510]["text"].startswith("Если я уверен, что стою на правильном пути")
