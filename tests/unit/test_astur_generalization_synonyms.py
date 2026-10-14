"""The «Обобщение» phrasings published by migration 7fd78c85f3b0.

The added answers are data that only reaches a database through that
migration, so its own merge function is checked here against the bank: the
result stays valid, every addition is reachable at the tier it was given,
no item's 0-point examples gain points, and an answer of one item does not
start scoring on another."""
import importlib.util
import re
from pathlib import Path

from app.services.astur.bank import load_v1_document, parse_bank
from app.services.astur.bank_validation import validate_bank
from app.services.astur.scoring import _ITEM_SCORERS, _Ctx, normalize
from app.services.astur.scoring_rules import get_rules

_MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / (
    "7fd78c85f3b0_publish_astur_generalization_synonyms.py"
)
_spec = importlib.util.spec_from_file_location("astur_generalization_synonyms", _MIGRATION)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)

BEFORE = load_v1_document()
AFTER = migration._with_additions(BEFORE)
LOCALES = ("ru", "kk")
score = _ITEM_SCORERS["open_text_tiers"]


def _items(document: dict) -> dict[str, dict]:
    return {i["item_id"]: i for s in document["subtests"] if s["key"] == "generalization" for i in s["items"]}


def _ctx(rules_version: str, locale: str = "ru") -> _Ctx:
    rules = get_rules(rules_version)
    return _Ctx(
        locale=locale,
        fold=rules.fold_text,
        any_locale=rules.answers_any_locale,
        kazakh_fold=rules.open_text_kazakh_fold,
    )


def _issues(document: dict) -> set[str]:
    return {str(issue.as_dict()) for issue in validate_bank(document, require_review=False)}


def test_the_merged_bank_has_no_new_validation_issues() -> None:
    assert _issues(AFTER) == _issues(BEFORE)
    parse_bank(AFTER)


def test_every_item_gets_more_phrasings_in_both_languages() -> None:
    before, after = _items(BEFORE), _items(AFTER)
    assert set(migration._ADDITIONS) == set(after)
    for item_id, item in after.items():
        for tier in ("score_2", "score_1"):
            for loc in LOCALES:
                assert len(item[tier][loc]) >= len(before[item_id][tier][loc])
        assert sum(len(item[t][loc]) for t in ("score_2", "score_1") for loc in LOCALES) > sum(
            len(before[item_id][t][loc]) for t in ("score_2", "score_1") for loc in LOCALES
        ), item_id


def test_every_addition_scores_its_own_tier_and_never_lowers_an_old_score() -> None:
    before, after = _items(BEFORE), _items(AFTER)
    for item_id, tiers in migration._ADDITIONS.items():
        for tier, by_locale in tiers.items():
            points = 2 if tier == "score_2" else 1
            for loc, phrases in by_locale.items():
                for phrase in phrases:
                    assert score(after[item_id], phrase, _ctx("4", loc)) == points, (item_id, phrase)
                    assert score(before[item_id], phrase, _ctx("4", loc)) <= points, (item_id, phrase)


def test_no_zero_point_example_gains_points() -> None:
    before, after = _items(BEFORE), _items(AFTER)
    for item_id, item in after.items():
        explanation = item["key_explanation"]["ru"]
        zeros = [z.strip() for z in re.sub(r"^.*?:", "", explanation).split(",") if z.strip()]
        assert zeros, item_id
        for zero in zeros:
            assert score(item, zero, _ctx("4")) == score(before[item_id], zero, _ctx("4")), (item_id, zero)


def test_answers_of_other_items_gain_no_new_credit_beyond_two_known_near_misses() -> None:
    """Typo tolerance on 8-letter words lets «общество» reach «вещество» and
    «әдебиет» reach «мәдениет» — the same closeness already exists in items 16
    and 5 of the old bank; anything else would be a new false credit."""
    before, after = _items(BEFORE), _items(AFTER)
    pool = {
        normalize(p, fold=True)
        for item in after.values()
        for tier in ("score_2", "score_1")
        for phrases in item[tier].values()
        for p in phrases
    }
    new_credit = set()
    for item_id, item in after.items():
        own = {normalize(p, fold=True) for t in ("score_2", "score_1") for ps in item[t].values() for p in ps}
        for phrase in pool - own:
            old = max(score(before[item_id], phrase, _ctx("3", loc)) for loc in LOCALES)
            if score(item, phrase, _ctx("4")) > old:
                new_credit.add((item_id, phrase))
    assert new_credit == {("generalization-14", "әдебиет"), ("generalization-15", "общество")}
