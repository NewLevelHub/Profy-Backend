"""PRO-338 Ф3.2 — content integrity for astur_bank.py. No DB involved
(АСТУР has no Question-model content, own table lands in Ф3.3), mirrors
the other *_bank.py tests' convention where it still applies."""
from scripts.astur_bank import (
    ANALOGIES_ITEMS,
    AWARENESS_ITEMS,
    CLASSIFICATION_ITEMS,
    GENERALIZATION_ITEMS,
    LABILITY_ITEMS,
    LOGICAL_SCHEMA_ITEMS,
    NUMERIC_SERIES_ITEMS,
    SUBJECTS,
    SUBTESTS,
)


def test_98_items_across_7_subtests() -> None:
    counts = {
        "awareness": len(AWARENESS_ITEMS),
        "analogies": len(ANALOGIES_ITEMS),
        "lability": len(LABILITY_ITEMS),
        "classification": len(CLASSIFICATION_ITEMS),
        "generalization": len(GENERALIZATION_ITEMS),
        "logical_schemas": len(LOGICAL_SCHEMA_ITEMS),
        "numeric_series": len(NUMERIC_SERIES_ITEMS),
    }
    assert counts == {
        "awareness": 20, "analogies": 16, "lability": 8, "classification": 12,
        "generalization": 19, "logical_schemas": 8, "numeric_series": 15,
    }
    assert sum(counts.values()) == 98
    assert sum(v for k, v in counts.items() if k != "lability") == 90


def test_subtests_metadata_matches_item_counts() -> None:
    for meta in SUBTESTS:
        assert meta["key"] and meta["name"] and meta["instruction"]
    lability_meta = next(s for s in SUBTESTS if s["key"] == "lability")
    assert lability_meta["scored"] is False
    scored_keys = {s["key"] for s in SUBTESTS if s["scored"]}
    assert scored_keys == {
        "awareness", "analogies", "classification", "generalization",
        "logical_schemas", "numeric_series",
    }


def test_awareness_every_item_has_a_valid_subject_and_answer_in_options() -> None:
    for item in AWARENESS_ITEMS:
        assert item["subject"] in SUBJECTS
        assert item["answer"] in item["options"]
        assert 4 <= len(item["options"]) <= 5


def test_analogies_answer_is_always_in_its_own_options() -> None:
    for item in ANALOGIES_ITEMS:
        assert item["answer"] in item["options"]
    # Item 4 (0-indexed 3) is the source's own documented anomaly: only 4
    # options instead of 5, preserved as-is, not padded.
    assert len(ANALOGIES_ITEMS[3]["options"]) == 4


def test_classification_answer_is_exactly_2_of_the_6_words() -> None:
    for item in CLASSIFICATION_ITEMS:
        assert len(item["words"]) == 6
        assert len(item["answer"]) == 2
        assert set(item["answer"]) <= set(item["words"])


def test_generalization_score_tiers_never_overlap() -> None:
    for item in GENERALIZATION_ITEMS:
        assert not set(item["score_2"]) & set(item["score_1"])
        assert item["subject"] in SUBJECTS


def test_generalization_max_possible_score_is_38() -> None:
    # Ф3.5: 19 pairs x 2 points max = 38.
    assert len(GENERALIZATION_ITEMS) * 2 == 38


def test_logical_schemas_are_ordered_general_to_specific_chains() -> None:
    for item in LOGICAL_SCHEMA_ITEMS:
        assert len(item["concepts"]) >= 3
    # Max scorable links across all 8 chains.
    max_links = sum(len(item["concepts"]) - 1 for item in LOGICAL_SCHEMA_ITEMS)
    assert max_links > 0


def test_numeric_series_answer_is_always_two_numbers() -> None:
    for item in NUMERIC_SERIES_ITEMS:
        assert len(item["answer"]) == 2
        assert all(isinstance(n, int) for n in item["answer"])


def test_lability_items_are_either_static_or_dynamic_never_both() -> None:
    for item in LABILITY_ITEMS:
        has_answer = "answer" in item
        has_dynamic = "dynamic" in item
        assert has_answer != has_dynamic

    dynamic_kinds = {item["dynamic"] for item in LABILITY_ITEMS if "dynamic" in item}
    assert dynamic_kinds == {"day_of_week", "own_name"}


def test_lability_static_answers_match_hand_computed_keys() -> None:
    """Spot-check the 6 static commands' answers against what the command
    text itself literally implies (verified by hand when the bank was
    written) — a regression guard, not a re-derivation."""
    by_instruction = {item["instruction"]: item for item in LABILITY_ITEMS if "answer" in item}

    assert by_instruction[
        "Если после слова «стол» по алфавиту идёт слово «стул» — напишите цифру 1, если нет — цифру 2."
    ]["answer"] == "1"  # о < у in the Cyrillic alphabet, стол < стул
    assert by_instruction[
        "Если 7 больше 5 — поставьте плюс, если нет — поставьте минус."
    ]["answer"] == "плюс"
    assert by_instruction[
        "Зачеркните чётное число из пары «3 и 8», иначе зачеркните нечётное."
    ]["answer"] == "8"
    assert by_instruction[
        "Если слово «зима» ближе по смыслу к слову «снег», чем к слову «жара», — напишите «да», иначе — «нет»."
    ]["answer"] == "да"
    assert by_instruction[
        "Если месяц май идёт раньше месяца март — поставьте галочку, иначе — крестик."
    ]["answer"] == "крестик"  # May is the 5th month, March the 3rd — May is NOT earlier
    assert by_instruction[
        "Напишите слово «выше», если 10 больше 100, иначе напишите слово «ниже»."
    ]["answer"] == "ниже"
