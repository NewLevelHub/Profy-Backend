"""Answers in either language score the same (scoring rules v4, PRO-480).

The respondent may switch language mid-attempt, so an answer is matched
against the keys of both languages, element by element: a word set or a
concept chain may mix ru and kk. That is only sound if a position means the
same thing in both lists — checked here exhaustively, over every possible
answer to every item of the real bank, not on a sample."""
from datetime import datetime, timedelta, timezone
from itertools import combinations, permutations, product

import pytest

from app.services.astur.scoring import _ITEM_SCORERS, _Ctx, _quick_item_correct, score_attempt
from app.services.astur.scoring_rules import get_rules
from tests.astur_fixtures import attempt_input, content_answers, quick_entries, v1_bank

BANK = v1_bank()
V3, V4 = get_rules("3"), get_rules("4")
LOCALES = ("ru", "kk")


def _ctx(locale: str, rules) -> _Ctx:
    return _Ctx(
        locale=locale,
        fold=rules.fold_text,
        any_locale=rules.answers_any_locale,
        kazakh_fold=rules.open_text_kazakh_fold,
    )


_PICK_FIELD = {"single_choice": "options", "pick_pair": "words", "chain_links": "concepts"}


def _candidates(method: str, size: int):
    """Every answer a respondent can give, as positions in the served list."""
    if method == "single_choice":
        return [[i] for i in range(size)]
    if method == "pick_pair":
        return [list(pair) for pair in combinations(range(size), 2)]
    if method == "chain_links":
        return [list(order) for order in permutations(range(size))]
    raise AssertionError(method)


def _pickable():
    for subtest in BANK.subtests:
        field = _PICK_FIELD.get(subtest.scoring_method)
        if field is not None:
            for item in subtest.items:
                yield subtest.scoring_method, item, item[field]


def _value(method: str, lists: dict, positions: list[int], languages) -> object:
    values = [lists[loc][p] for p, loc in zip(positions, languages)]
    return values[0] if method == "single_choice" else values


def _all(locale: str) -> list[str]:
    return [locale] * 8


@pytest.mark.parametrize("rules", [V3, V4], ids=["v3", "v4"])
def test_every_answer_scores_the_same_in_the_attempts_own_language(rules) -> None:
    checked = 0
    for method, item, lists in _pickable():
        scorer = _ITEM_SCORERS[method]
        for positions in _candidates(method, len(lists["ru"])):
            ru = scorer(item, _value(method, lists, positions, _all("ru")), _ctx("ru", rules))
            kk = scorer(item, _value(method, lists, positions, _all("kk")), _ctx("kk", rules))
            assert ru == kk, (item["item_id"], positions)
            checked += 1
    assert checked == 763  # every answer to every pickable item of bank v1


def test_v4_an_answer_in_the_other_language_scores_the_same() -> None:
    """RU attempt answered in Kazakh and KK attempt answered in Russian score
    exactly as in the attempt's own language — wrong answers included (0)."""
    for method, item, lists in _pickable():
        scorer = _ITEM_SCORERS[method]
        for positions in _candidates(method, len(lists["ru"])):
            expected = scorer(item, _value(method, lists, positions, _all("ru")), _ctx("ru", V4))
            for attempt_locale, answer_locale in (("ru", "kk"), ("kk", "ru")):
                value = _value(method, lists, positions, _all(answer_locale))
                assert scorer(item, value, _ctx(attempt_locale, V4)) == expected, (item["item_id"], positions)


def test_v3_still_scores_only_the_attempts_own_language() -> None:
    """Frozen versions keep their rule: the other language scored 0 before v4."""
    item = BANK.subtest("awareness").items[0]
    assert _ITEM_SCORERS["single_choice"](item, item["answer"]["kk"], _ctx("ru", V3)) == 0
    assert _ITEM_SCORERS["single_choice"](item, item["answer"]["kk"], _ctx("ru", V4)) == 1


def test_v4_an_answer_mixing_both_languages_scores_like_one_language() -> None:
    """A word set or concept chain with some elements in ru and some in kk is
    matched element by element — mixing never costs a point."""
    checked = 0
    for method, item, lists in _pickable():
        if method == "single_choice":
            continue
        scorer = _ITEM_SCORERS[method]
        for positions in _candidates(method, len(lists["ru"])):
            expected = scorer(item, _value(method, lists, positions, _all("ru")), _ctx("ru", V4))
            if method == "pick_pair":
                masks = list(product(LOCALES, repeat=2))
            else:
                masks = [[LOCALES[(i + shift) % 2] for i in range(len(positions))] for shift in (0, 1)]
            for languages in masks:
                value = _value(method, lists, positions, list(languages))
                for attempt_locale in LOCALES:
                    assert scorer(item, value, _ctx(attempt_locale, V4)) == expected, (item["item_id"], value)
                    checked += 1
    assert checked > 2000


def test_v4_values_from_neither_language_score_zero() -> None:
    awareness = BANK.subtest("awareness").items[0]
    classification = BANK.subtest("classification").items[0]
    chain = BANK.subtest("logical_schemas").items[0]
    generalization = BANK.subtest("generalization").items[0]
    assert _ITEM_SCORERS["single_choice"](awareness, "не вариант", _ctx("ru", V4)) == 0
    assert _ITEM_SCORERS["pick_pair"](classification, ["не", "вариант"], _ctx("kk", V4)) == 0
    assert _ITEM_SCORERS["chain_links"](chain, ["а", "б", "в"], _ctx("ru", V4)) == 0
    assert _ITEM_SCORERS["open_text_tiers"](generalization, "что-то совсем другое", _ctx("kk", V4)) == 0


def test_every_quick_command_choice_scores_the_same_in_either_language() -> None:
    lability = BANK.subtest("lability")
    monday = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)
    names = ["Тимур", "Айгерим", "Ерлан", "Ұлжан", "Arman", "Dana"]
    for name, day, item, position in product(names, range(7), lability.items, range(2)):
        answered_at = (monday + timedelta(days=day)).isoformat()
        results = set()
        for attempt_locale, answer_locale in product(LOCALES, LOCALES):
            attempt = attempt_input(BANK, {}, profile_name=name, locale=attempt_locale)
            entry = {"answer": item["options"][answer_locale][position], "answered_at": answered_at}
            results.add(_quick_item_correct(item, entry, attempt, V4, _ctx(attempt_locale, V4)))
        assert len(results) == 1, (item["item_id"], name, day, position)


def _kk_value(subtest_key: str, item: dict, ru_value):
    """The ru answer in kk, position for position."""
    field = {"awareness": "options", "analogies": "options", "classification": "words",
             "logical_schemas": "concepts"}.get(subtest_key)
    if field is None:
        return ru_value
    ru, kk = item[field]["ru"], item[field]["kk"]
    return [kk[ru.index(v)] for v in ru_value] if isinstance(ru_value, list) else kk[ru.index(ru_value)]


@pytest.mark.parametrize("wrong", [frozenset(), frozenset({"awareness", "classification", "logical_schemas"})])
def test_a_whole_attempt_scores_the_same_whatever_language_it_is_answered_in(wrong) -> None:
    ru_answers = content_answers(BANK, wrong=wrong)
    baseline = score_attempt(BANK, attempt_input(BANK, ru_answers), V4)
    keys = [s.key for s in BANK.subtests]
    # Every block in kk, and alternating blocks (a switch between blocks).
    for kk_keys in (set(keys), set(keys[::2]), set(keys[1::2])):
        answers = {
            key: {
                pos: _kk_value(key, BANK.subtest(key).items[int(pos) - 1], value) if key in kk_keys else value
                for pos, value in block.items()
            }
            for key, block in ru_answers.items()
        }
        lability = quick_entries(BANK, locale="kk") if "lability" in kk_keys else quick_entries(BANK)
        for attempt_locale in LOCALES:
            attempt = attempt_input(BANK, answers, lability, locale=attempt_locale)
            # The whole frozen result: subtests, overall, knowledge profile,
            # numeric gap, quick commands, protocol quality.
            assert score_attempt(BANK, attempt, V4).model_dump() == baseline.model_dump()


def _all_phrases() -> set[str]:
    generalization = BANK.subtest("generalization")
    return {
        phrase
        for item in generalization.items
        for tier in ("score_2", "score_1")
        for phrases in item[tier].values()
        for phrase in phrases
    }


def _typos(phrase: str) -> list[str]:
    """A dropped last letter and a swapped middle pair — the kind of slip the
    fuzzy fallback exists for."""
    variants = [phrase[:-1]]
    if len(phrase) > 3:
        mid = len(phrase) // 2
        variants.append(phrase[:mid - 1] + phrase[mid] + phrase[mid - 1] + phrase[mid + 1:])
    return variants


def test_v4_open_text_score_is_the_best_of_the_per_language_scores() -> None:
    """v4 is exactly the best of the one-language scores (same matching rules
    otherwise), never takes a point away from v3 in the attempt's own
    language, and does not depend on the attempt's language."""
    scorer = _ITEM_SCORERS["open_text_tiers"]
    phrases = _all_phrases()
    answers = phrases | {typo for phrase in phrases for typo in _typos(phrase)} | {"что-то совсем другое"}
    one_language = {loc: _Ctx(locale=loc, fold=True, kazakh_fold=True) for loc in LOCALES}
    for item in BANK.subtest("generalization").items:
        for answer in answers:
            best = max(scorer(item, answer, one_language[loc]) for loc in LOCALES)
            for loc in LOCALES:
                got = scorer(item, answer, _ctx(loc, V4))
                assert got == best, (item["item_id"], answer)
                assert got >= scorer(item, answer, _ctx(loc, V3)), (item["item_id"], answer)


_RU_LAYOUT = str.maketrans("әғқңөұүһі", "агкноуухи")


def test_v4_accepts_kazakh_answers_typed_without_kazakh_letters() -> None:
    """«кылкан жапыракты агаштар» for «қылқан жапырақты ағаштар»: every kk
    phrasing typed on a Russian layout keeps its points (v3 lost most)."""
    scorer = _ITEM_SCORERS["open_text_tiers"]
    lost_in_v3 = 0
    for item in BANK.subtest("generalization").items:
        for tier, points in (("score_2", 2), ("score_1", 1)):
            for phrase in item[tier]["kk"]:
                typed = phrase.translate(_RU_LAYOUT)
                assert scorer(item, typed, _ctx("kk", V4)) == points, (item["item_id"], typed)
                assert scorer(item, typed.replace("и", "i"), _ctx("kk", V4)) == points  # Latin "i" for «і»
                lost_in_v3 += scorer(item, typed, _ctx("kk", V3)) < points
    assert lost_in_v3 > 10


def test_kazakh_letter_folding_never_touches_choice_answers() -> None:
    """Two options could fold into one string — choices still match exactly."""
    item = {"options": {"kk": ["қол", "кол"]}, "answer": {"kk": "қол"}}
    single_choice = _ITEM_SCORERS["single_choice"]
    assert single_choice(item, "кол", _ctx("kk", V4)) == 0
    assert single_choice(item, "қол", _ctx("kk", V4)) == 1


def test_another_languages_exact_tier_never_caps_a_better_typo_match() -> None:
    """A phrase that is exactly a kk 1-point synonym and a typo of a ru
    2-point one keeps its 2 points (a merged tier list would give 1)."""
    item = {
        "score_2": {"ru": ["хвойные деревья"], "kk": ["қылқан жапырақты ағаштар"]},
        "score_1": {"ru": ["деревья"], "kk": ["хвойные деревя"]},
    }
    scorer = _ITEM_SCORERS["open_text_tiers"]
    assert scorer(item, "хвойные деревя", _ctx("ru", V3)) == 2
    assert scorer(item, "хвойные деревя", _ctx("kk", V3)) == 1
    assert scorer(item, "хвойные деревя", _ctx("ru", V4)) == 2
    assert scorer(item, "хвойные деревя", _ctx("kk", V4)) == 2
