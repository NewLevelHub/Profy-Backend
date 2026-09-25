"""PRO-427 — the АСТУР bank document and its pre-publish validation."""
import copy

from app.services.astur.bank import content_hash, load_v1_document, parse_bank, stimulus_manifest
from app.services.astur.bank_validation import validate_bank
from tests.astur_fixtures import v1_document

# v1 is the immutable pre-PRO-427 bank; every legacy attempt is pinned to it.
# Changing app/data/astur_bank_v1.json would silently fork fresh databases
# from production — any content change must be a new published version.
V1_CONTENT_HASH = "fe7e5127744300935ccab117038032766cd0ac01c25558e2dfa91fa8ca0122e4"


def reviewed(document: dict) -> dict:
    """A copy of `document` that satisfies the review requirements every new
    version must meet (difficulty, second-reviewer check, key explanation)."""
    doc = copy.deepcopy(document)
    for subtest in doc["subtests"]:
        for item in subtest["items"]:
            item["difficulty"] = item.get("difficulty") or "medium"
            item["review_status"] = "reviewed"
            item["key_explanation"] = item.get("key_explanation") or {"ru": "Проверено."}
    return doc


def _codes(document: dict, **kwargs) -> set[str]:
    kwargs.setdefault("require_review", False)
    return {issue.code for issue in validate_bank(document, **kwargs)}


def _item(document: dict, subtest_key: str, index: int = 0) -> dict:
    return next(s for s in document["subtests"] if s["key"] == subtest_key)["items"][index]


def test_v1_document_is_frozen() -> None:
    assert content_hash(load_v1_document()) == V1_CONTENT_HASH


def test_v1_passes_structural_validation() -> None:
    assert validate_bank(load_v1_document(), require_review=False) == []


def test_a_new_version_must_be_reviewed_before_publishing() -> None:
    issues = validate_bank(load_v1_document())
    assert {i.code for i in issues} == {"review_required"}
    fields = {i.field for i in issues}
    assert fields == {"difficulty", "review_status", "key_explanation"}
    assert validate_bank(reviewed(load_v1_document())) == []


def test_key_explanation_is_required_only_for_meaning_based_items() -> None:
    doc = reviewed(load_v1_document())
    _item(doc, "awareness")["key_explanation"] = None
    assert validate_bank(doc) == []
    _item(doc, "analogies")["key_explanation"] = {"ru": " "}
    assert {i.field for i in validate_bank(doc)} == {"key_explanation"}


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
    assert validate_bank(doc, require_review=False) == []


def test_duplicate_item_id_is_rejected() -> None:
    doc = v1_document()
    _item(doc, "analogies")["item_id"] = _item(doc, "awareness")["item_id"]
    assert "duplicate_item_id" in _codes(doc)


def test_quick_instructions_keep_an_even_number_of_commands() -> None:
    doc = v1_document()
    next(s for s in doc["subtests"] if s["key"] == "lability")["items"].pop()
    assert "wrong_item_count" in _codes(doc)


def test_figure_items_resolve_their_images_by_item_id() -> None:
    doc = v1_document()
    figures = next(s for s in doc["subtests"] if s["key"] == "geometric_figures")["items"]
    figures.reverse()  # reordering is safe: pictures follow item_id
    assert _codes(doc) == set()

    figures[0]["item_id"] = "geometric_figures-99"
    assert "unknown_stimulus" in _codes(doc)


def test_pinned_stimulus_must_match_the_manifest() -> None:
    doc = v1_document()
    item = _item(doc, "geometric_figures")
    item["stimulus"] = copy.deepcopy(stimulus_manifest()[item["item_id"]])
    assert _codes(doc) == set()
    item["stimulus"]["target"]["sha256"] = "0" * 64
    assert "stimulus_mismatch" in _codes(doc)


def test_figure_options_must_be_the_image_letters() -> None:
    doc = v1_document()
    item = _item(doc, "geometric_figures")
    item["options"] = {"ru": ["А", "Б", "В", "Д"], "kk": ["А", "Б", "В", "Д"]}
    item["answer"] = {"ru": "А", "kk": "А"}
    assert "stimulus_mismatch" in _codes(doc)


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
    assert _codes(doc, base=base, confirmed_item_ids={item["item_id"]}) == set()


def test_wording_only_change_needs_no_key_confirmation() -> None:
    base = parse_bank(load_v1_document())
    doc = v1_document()
    _item(doc, "awareness")["text"]["ru"] = "Новая формулировка вопроса …?"
    assert _codes(doc, base=base) == set()


def test_malformed_document_reports_instead_of_raising() -> None:
    assert _codes({"subtests": "nope"}) == {"invalid_structure"}
