"""PRO-448 — specialist interpretation of the psychoemotional test."""
import itertools

from app.i18n import use_locale
from app.i18n.catalog import tr
from app.i18n.catalog.psychoemotional_interpretation import KK, RU
from app.services.psychoemotional.constants import BASIC_COLOR_IDS, COLOR_IDS, EXTRA_COLOR_IDS
from app.services.psychoemotional.engine import compute
from app.services.psychoemotional.interpretation import interpret


def _interpret(list1: list[int], list2: list[int]):
    return interpret(compute(list1, list2).as_dict(), list1, list2)


def _flat(tree: dict) -> list[str]:
    return [s for v in tree.values() for s in (_flat(v) if isinstance(v, dict) else [v])]


def test_reference_run_matches_the_expected_blocks() -> None:
    # The public 8-colour example on psytests.org (СО 22, ВК ≈ 0.63 there too).
    result = _interpret([3, 1, 6, 0, 5, 2, 7, 4], [0, 5, 1, 2, 4, 3, 7, 6])
    texts = RU

    assert result.reading == [texts["reading"]["split"], texts["reading"]["d_high"]]
    assert [(h.key, h.position_depth) for h in result.highlights] == [
        ("comp.0.1", 3),
        ("comp.5.forward", 2),
        ("anxiety.3.6", 1),
    ]
    assert [(n.metric, n.level) for n in result.indices] == [("anxiety", "low"), ("so", "elevated"), ("vk", "reduced")]
    assert [(p.sign, p.colors) for p in result.positions] == [
        ("plus", [0, 5]),
        ("cross", [1, 2]),
        ("equal", [4, 3]),
        ("minus", [7, 6]),
        ("plus_minus", [0, 6]),
    ]
    # pairs are keyed by sorted ids, the root conflict keeps its direction
    assert [p.text for p in result.positions] == [
        texts["pair"]["plus"]["05"],
        texts["pair"]["cross"]["12"],
        texts["pair"]["equal"]["34"],
        texts["pair"]["minus"]["67"],
        texts["pm"]["06"],
    ]
    assert all(position.details == [] for position in result.positions)
    assert [(group.sign, group.colors, group.stable) for group in result.mcv_groups] == [
        ("plus", [0], False),
        ("plus", [5], False),
        ("cross", [1], False),
        ("cross", [2], False),
        ("equal", [4], False),
        ("equal", [3], False),
        ("minus", [7], False),
        ("minus", [6], False),
    ]
    assert [(prompt.key, prompt.text) for prompt in result.conversation_prompts] == [
        ("leading", texts["conversation"]["leading"]["0"]),
        ("tension", texts["conversation"]["tension"]["6"]),
        ("so_elevated", texts["conversation"]["so"]["elevated"]),
        ("vk_reduced", texts["conversation"]["vk"]["reduced"]),
    ]


def test_a_link_replaces_the_separate_notes_about_its_two_colours() -> None:
    list2 = [6, 3, 4, 2, 5, 0, 7, 1]  # blue last, brown first
    result = _interpret(list2, list2)
    assert [h.key for h in result.highlights] == ["link.1.6"]


def test_high_anxiety_orders_highlights_by_position_depth() -> None:
    list2 = [6, 0, 1, 5, 7, 2, 3, 4]  # green 6, red 7, yellow 8 → anxiety 6 (high)
    result = _interpret(list2, list2)

    assert result.indices[0].level == "high"
    assert [(h.key, h.position_depth) for h in result.highlights] == [
        ("link.4.6", 3),
        ("anxiety.3.7", 2),
        ("comp.0.2", 2),
        ("anxiety.2.6", 1),
    ]
    assert result.positions[-1].text == RU["pm"]["64"]  # brown first, yellow last


def test_texts_follow_the_request_locale() -> None:
    list2 = [0, 5, 1, 2, 4, 3, 7, 6]
    with use_locale("kk"):
        result = _interpret(list2, list2)
    assert result.positions[0].text == KK["pair"]["plus"]["05"]
    assert result.mcv_groups[0].text == KK["pair"]["plus"]["05"]
    assert result.indices[1].text == KK["level"]["so"]["elevated"]
    assert result.conversation_prompts[0].text == KK["conversation"]["leading"]["0"]


def test_a_stable_run_has_no_reading_notes() -> None:
    # Run quality is shown as the card's validity badge, never repeated as text.
    list2 = [0, 5, 1, 2, 4, 3, 7, 6]
    result = _interpret(list2, list2)
    assert result.reading == []


def test_every_pickable_key_has_a_text_in_both_locales() -> None:
    unordered = {f"{a}{b}" for a, b in itertools.combinations(sorted(COLOR_IDS), 2)}
    ordered = {f"{a}{b}" for a, b in itertools.permutations(sorted(COLOR_IDS), 2)}
    for tree in (RU, KK):
        assert set(tree["reading"]) == {"split", "d_high"}
        assert set(tree["pair"]) == {"plus", "cross", "equal", "minus"}
        assert all(set(pairs) == unordered for pairs in tree["pair"].values())
        assert set(tree["single"]) == {"plus", "cross", "equal", "minus"}
        assert all(
            set(notes) == {str(color_id) for color_id in COLOR_IDS}
            for notes in tree["single"].values()
        )
        assert set(tree["pm"]) == ordered
        assert set(tree["anxiety"]) == {f"{c}.{p}" for c in BASIC_COLOR_IDS for p in (6, 7, 8)}
        assert set(tree["comp"]) == {f"{c}.{p}" for c in EXTRA_COLOR_IDS for p in (1, 2, 3)} | {"5.forward"}
        assert set(tree["level"]["anxiety"]) == {"low", "moderate", "high", "very_high"}
        assert set(tree["level"]["so"]) == {"norm", "elevated", "high"}
        assert set(tree["level"]["vk"]) == {"low_tone", "reduced", "balance", "overexcited"}
        assert set(tree["conversation"]["leading"]) == {str(color_id) for color_id in COLOR_IDS}
        assert set(tree["conversation"]["tension"]) == {str(color_id) for color_id in COLOR_IDS}
        assert set(tree["conversation"]["anxiety"]) == {"moderate", "high", "very_high"}
        assert set(tree["conversation"]["so"]) == {"elevated", "high"}
        assert set(tree["conversation"]["vk"]) == {"low_tone", "reduced", "overexcited"}


def test_any_ordering_interprets_without_a_missing_key() -> None:
    for list2 in itertools.islice(itertools.permutations(range(8)), 0, 40320, 97):
        result = _interpret(list(list2), list(list2))
        assert len(result.indices) == 3 and len(result.positions) == 5
        assert all(position.details == [] for position in result.positions)
        assert 4 <= len(result.mcv_groups) <= 8
        assert 2 <= len(result.conversation_prompts) <= 5


def test_auxiliary_colours_at_the_end_are_not_described_as_anxiety() -> None:
    for locale_tree in (RU, KK):
        for color_id in (0, 5, 6, 7):
            text = locale_tree["single"]["minus"][str(color_id)].lower()
            assert "риск" not in text
            assert "жасырын кернеу" not in text


def test_no_clinical_labels_or_trademark_in_any_text() -> None:
    banned = ("депресс", "невроз", "патолог", "расстройств", "дезадаптац", "диагноз", "люшер")
    for text in _flat(RU) + _flat(KK):
        assert not any(word in text.lower() for word in banned), text


def test_catalog_is_registered() -> None:
    assert tr("psychoemotional_interpretation", locale="ru") is RU
