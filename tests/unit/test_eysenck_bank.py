"""PRO-338 Ф1.4 — content integrity for eysenck_bank.py's key. No DB
involved, mirrors test_professional_types_bank.py's convention."""
from scripts.eysenck_bank import QUESTIONS

_SCALES = {"extraversion", "neuroticism", "lie"}


def test_has_exactly_57_items() -> None:
    assert len(QUESTIONS) == 57


def test_orders_are_unique_and_contiguous_from_410() -> None:
    orders = [q["order"] for q in QUESTIONS]
    assert orders == list(range(410, 467))


def test_every_item_has_exactly_one_scale_and_a_keyed_direction() -> None:
    for q in QUESTIONS:
        assert q["scale"] in _SCALES
        assert q["keyed"] in {"yes", "no"}


def test_scale_item_counts_match_the_source_key() -> None:
    by_scale: dict[str, list[dict]] = {"extraversion": [], "neuroticism": [], "lie": []}
    for q in QUESTIONS:
        by_scale[q["scale"]].append(q)

    assert len(by_scale["extraversion"]) == 24
    assert len(by_scale["neuroticism"]) == 24
    assert len(by_scale["lie"]) == 9

    # Neuroticism has no "Нет" side in the source key — every neuroticism
    # item must be keyed "yes".
    assert all(q["keyed"] == "yes" for q in by_scale["neuroticism"])

    extraversion_yes = sum(1 for q in by_scale["extraversion"] if q["keyed"] == "yes")
    extraversion_no = sum(1 for q in by_scale["extraversion"] if q["keyed"] == "no")
    assert (extraversion_yes, extraversion_no) == (15, 9)

    lie_yes = sum(1 for q in by_scale["lie"] if q["keyed"] == "yes")
    lie_no = sum(1 for q in by_scale["lie"] if q["keyed"] == "no")
    assert (lie_yes, lie_no) == (3, 6)


def test_specific_items_match_the_source_spec_verbatim() -> None:
    """A handful of individually-verifiable anchors against the key in
    02-Фаза1-Лёгкие-тесты.md §1.Б, not exhaustive — the count-based test
    above already proves the aggregate shape."""
    by_order = {q["order"]: q for q in QUESTIONS}

    # Item 1 -> order 410 -> extraversion, "yes"
    assert (by_order[410]["scale"], by_order[410]["keyed"]) == ("extraversion", "yes")
    # Item 41 -> order 450 -> extraversion, "no" (last of the extraversion-no set)
    assert (by_order[450]["scale"], by_order[450]["keyed"]) == ("extraversion", "no")
    # Item 36 -> order 445 -> lie, "yes"
    assert (by_order[445]["scale"], by_order[445]["keyed"]) == ("lie", "yes")
    # Item 12 -> order 421 -> lie, "no"
    assert (by_order[421]["scale"], by_order[421]["keyed"]) == ("lie", "no")
    # Item 57 -> order 466 -> neuroticism, "yes"
    assert (by_order[466]["scale"], by_order[466]["keyed"]) == ("neuroticism", "yes")
