"""PRO-338 Ф1.9 — content integrity for boyko_empathy_bank.py's key. No DB
involved, mirrors test_elers_bank.py's convention."""
from scripts.boyko_empathy_bank import QUESTIONS

_CHANNELS = {"rational", "emotional", "intuitive", "attitudes", "penetration", "identification"}


def test_has_exactly_36_items() -> None:
    assert len(QUESTIONS) == 36


def test_orders_are_unique_and_contiguous_from_511() -> None:
    orders = [q["order"] for q in QUESTIONS]
    assert orders == list(range(511, 547))


def test_every_item_has_a_channel_and_keyed_direction() -> None:
    for q in QUESTIONS:
        assert q["channel"] in _CHANNELS
        assert q["keyed"] in {"yes", "no"}


def test_every_channel_has_exactly_6_items() -> None:
    by_channel: dict[str, list[dict]] = {c: [] for c in _CHANNELS}
    for q in QUESTIONS:
        by_channel[q["channel"]].append(q)

    for channel, items in by_channel.items():
        assert len(items) == 6, f"channel {channel} should have 6 items, got {len(items)}"


def test_specific_items_match_the_source_key_verbatim() -> None:
    """A handful of individually-verifiable anchors against
    docs/psych/new-tests-content-sources.md's key, not exhaustive — the
    count-based tests above already prove the aggregate shape."""
    by_order = {q["order"]: q for q in QUESTIONS}

    # Item 1 -> order 511 -> rational, "yes"
    assert by_order[511]["channel"] == "rational"
    assert by_order[511]["keyed"] == "yes"
    # Item 2 -> order 512 -> emotional, "no"
    assert by_order[512]["channel"] == "emotional"
    assert by_order[512]["keyed"] == "no"
    # Item 36 -> order 546 -> identification, "no" (the item whose text this
    # ticket's own audit had to restore, along with 32-35)
    assert by_order[546]["channel"] == "identification"
    assert by_order[546]["keyed"] == "no"
    assert by_order[546]["text"].startswith("Мне трудно понять, почему пустяки")
