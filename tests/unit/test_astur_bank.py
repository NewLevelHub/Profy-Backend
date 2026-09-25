"""PRO-427 — the АСТУР bank document and its pre-publish validation."""
from app.services.astur.bank import content_hash, load_v1_document, parse_bank
from app.services.astur.bank_validation import validate_bank
from tests.astur_fixtures import v1_document

# v1 is the immutable pre-PRO-427 bank; every legacy attempt is pinned to it.
# Changing app/data/astur_bank_v1.json would silently fork fresh databases
# from production — any content change must be a new published version.
V1_CONTENT_HASH = "ae0fdc07ba4d7821b91c1a8f2b389386faccb992694d417f6c483f5b705b4664"


def _codes(document: dict, **kwargs) -> set[str]:
    return {issue.code for issue in validate_bank(document, **kwargs)}


def _item(document: dict, subtest_key: str, index: int = 0) -> dict:
    return next(s for s in document["subtests"] if s["key"] == subtest_key)["items"][index]


def test_v1_document_is_frozen() -> None:
    assert content_hash(load_v1_document()) == V1_CONTENT_HASH


def test_v1_passes_validation() -> None:
    assert validate_bank(load_v1_document()) == []


def test_v1_shape_and_maximums_are_derived_from_the_bank() -> None:
    bank = parse_bank(load_v1_document())
    assert [s.key for s in sorted(bank.subtests, key=lambda s: s.number)] == [
        "awareness", "analogies", "lability", "classification",
        "generalization", "logical_schemas", "numeric_series", "geometric_figures",
    ]
    assert bank.max_scores() == {
        "awareness": 20, "analogies": 16, "classification": 12, "generalization": 38,
        "logical_schemas": 26, "numeric_series": 15, "geometric_figures": 5,
    }
    item_ids = [item["item_id"] for s in bank.subtests for item in s.items]
    assert len(item_ids) == len(set(item_ids)) == 103


def test_key_missing_from_options_is_rejected() -> None:
    doc = v1_document()
    _item(doc, "awareness")["answer"]["ru"] = "нет такого варианта"
    assert "key_not_in_options" in _codes(doc)


def test_ru_and_kk_keys_must_point_at_the_same_option() -> None:
    doc = v1_document()
    item = _item(doc, "analogies")
    kk_options = item["options"]["kk"]
    item["answer"]["kk"] = next(o for o in kk_options if o != item["answer"]["kk"])
    assert "key_locale_mismatch" in _codes(doc)


def test_ru_kk_structure_mismatch_is_rejected() -> None:
    doc = v1_document()
    _item(doc, "awareness")["options"]["kk"].pop()
    assert "locale_structure_mismatch" in _codes(doc)


def test_missing_translation_is_rejected() -> None:
    doc = v1_document()
    _item(doc, "awareness")["text"]["kk"] = "  "
    assert "missing_translation" in _codes(doc)


def test_open_answer_synonym_tiers_must_not_be_empty_or_overlap() -> None:
    doc = v1_document()
    _item(doc, "generalization")["score_2"]["ru"] = []
    assert "wrong_item_shape" in _codes(doc)

    doc = v1_document()
    item = _item(doc, "generalization")
    item["score_1"]["ru"].append(item["score_2"]["ru"][0])
    assert "ambiguous_tiers" in _codes(doc)


def test_synonym_tiers_may_differ_in_length_between_languages() -> None:
    doc = v1_document()
    _item(doc, "generalization")["score_1"]["kk"].append("тағы бір синоним")
    assert validate_bank(doc) == []


def test_duplicate_item_id_is_rejected() -> None:
    doc = v1_document()
    _item(doc, "analogies")["item_id"] = _item(doc, "awareness")["item_id"]
    assert "duplicate_item_id" in _codes(doc)


def test_asset_backed_and_paired_subtests_keep_their_item_counts() -> None:
    doc = v1_document()
    figures = next(s for s in doc["subtests"] if s["key"] == "geometric_figures")
    figures["items"].pop()
    assert "wrong_item_count" in _codes(doc)

    doc = v1_document()
    quick = next(s for s in doc["subtests"] if s["key"] == "lability")
    quick["items"].pop()
    assert "wrong_item_count" in _codes(doc)


def test_subtest_cannot_change_its_scoring_method() -> None:
    doc = v1_document()
    next(s for s in doc["subtests"] if s["key"] == "analogies")["scoring_method"] = "open_text_tiers"
    assert "invalid_structure" in _codes(doc)


def test_changed_key_needs_confirmation_against_the_base_version() -> None:
    base = parse_bank(load_v1_document())
    doc = v1_document()
    item = _item(doc, "awareness")
    item["options"]["ru"][0] = "новый вариант"
    item["options"]["kk"][0] = "жаңа нұсқа"

    assert _codes(doc, base=base) == {"key_confirmation_required"}
    assert validate_bank(doc, base=base, confirmed_item_ids={item["item_id"]}) == []


def test_wording_only_change_needs_no_key_confirmation() -> None:
    base = parse_bank(load_v1_document())
    doc = v1_document()
    _item(doc, "awareness")["text"]["ru"] = "Новая формулировка вопроса …?"
    assert validate_bank(doc, base=base) == []


def test_malformed_document_reports_instead_of_raising() -> None:
    assert _codes({"subtests": "nope"}) == {"invalid_structure"}
