"""PRO-338 Ф1.10 — content integrity for kondash_anxiety_bank.py's
subscale structure. No DB involved, mirrors test_elers_bank.py's/
test_boyko_empathy_bank.py's convention."""
from scripts.kondash_anxiety_bank import QUESTIONS


def test_has_exactly_40_items() -> None:
    assert len(QUESTIONS) == 40


def test_orders_are_unique_and_contiguous_from_547() -> None:
    orders = [q["order"] for q in QUESTIONS]
    assert orders == list(range(547, 587))


def test_every_item_belongs_to_one_of_the_4_subscales() -> None:
    for q in QUESTIONS:
        assert q["subscale"] in {"school", "self_esteem", "interpersonal", "magical"}


def test_subscale_counts_match_the_source_audit() -> None:
    by_subscale: dict[str, list[dict]] = {"school": [], "self_esteem": [], "interpersonal": [], "magical": []}
    for q in QUESTIONS:
        by_subscale[q["subscale"]].append(q)

    assert len(by_subscale["school"]) == 10
    assert len(by_subscale["self_esteem"]) == 10
    assert len(by_subscale["interpersonal"]) == 10
    assert len(by_subscale["magical"]) == 10


def test_specific_items_match_the_source_subscale_key_verbatim() -> None:
    """A handful of individually-verifiable anchors against
    docs/psych/new-tests-content-sources.md's key, not exhaustive — the
    count-based test above already proves the aggregate shape."""
    by_order = {q["order"]: q for q in QUESTIONS}

    # Item 1 -> order 547 -> school ("Отвечать у доски.")
    assert by_order[547]["subscale"] == "school"
    assert by_order[547]["text"]["ru"] == "Отвечать у доски."
    # Item 14 -> order 560 -> magical — the item whose 2026-09-15
    # reconstruction was wrong, corrected to the confirmed original text.
    assert by_order[560]["subscale"] == "magical"
    assert by_order[560]["text"]["ru"] == (
        "Мысль о том, что неосторожным поступком можно навлечь на себя гнев потусторонних сил."
    )
    # Item 22 -> order 568 -> interpersonal (one of the 11 items missing
    # before the 2026-09-16 correction)
    assert by_order[568]["subscale"] == "interpersonal"
    assert by_order[568]["text"]["ru"] == "Выступать перед большой аудиторией."
    # Item 40 -> order 586 -> magical (last item)
    assert by_order[586]["subscale"] == "magical"
