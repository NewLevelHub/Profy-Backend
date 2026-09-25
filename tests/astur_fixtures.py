"""Shared АСТУР test data built from the real v1 bank document (PRO-427)."""
import copy
from datetime import datetime, timezone

from app.services.astur.bank import AsturBank, load_v1_document, parse_bank
from app.services.astur.scoring import AttemptInput, _day_of_week_expected, _own_name_expected

PROFILE_NAME = "Тимур Ахметов"  # consonant first letter → own-name command expects "нет"
ANSWERED_AT = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)  # Monday in Asia/Almaty


def v1_document() -> dict:
    return copy.deepcopy(load_v1_document())


def v1_bank() -> AsturBank:
    return parse_bank(load_v1_document())


def correct_answer(subtest_key: str, item: dict, locale: str = "ru"):
    if subtest_key in ("awareness", "analogies", "geometric_figures"):
        return item["answer"][locale]
    if subtest_key == "classification":
        return list(item["answer"][locale])
    if subtest_key == "generalization":
        return item["score_2"][locale][0]
    if subtest_key == "logical_schemas":
        return list(item["concepts"][locale])
    if subtest_key == "numeric_series":
        return list(item["answer"])
    raise AssertionError(subtest_key)


def wrong_answer(subtest_key: str, item: dict, locale: str = "ru"):
    """A value in the right format (accepted at submit) that scores 0."""
    if subtest_key in ("awareness", "analogies", "geometric_figures"):
        return next(o for o in item["options"][locale] if o != item["answer"][locale])
    if subtest_key == "classification":
        return [w for w in item["words"][locale] if w not in item["answer"][locale]][:2]
    if subtest_key == "generalization":
        return "что-то совсем другое"
    if subtest_key == "logical_schemas":
        concepts = item["concepts"][locale]
        # No forward-adjacent pair survives: reversed order.
        return concepts[::-1]
    if subtest_key == "numeric_series":
        return [item["answer"][0] + 1, item["answer"][1] + 1]
    raise AssertionError(subtest_key)


def content_answers(bank: AsturBank, *, locale: str = "ru", wrong: set[str] | frozenset = frozenset()) -> dict:
    """Every content subtest fully and correctly answered, except subtests in
    `wrong`, answered with valid-format but wrong values."""
    answers: dict[str, dict] = {}
    for subtest in bank.subtests:
        if subtest.key == "lability":
            continue
        pick = wrong_answer if subtest.key in wrong else correct_answer
        answers[subtest.key] = {
            str(i): pick(subtest.key, item, locale) for i, item in enumerate(subtest.items, start=1)
        }
    return answers


def expected_quick_answer(item: dict, *, locale: str = "ru", timezone_name: str = "Asia/Almaty") -> str:
    options = item["options"][locale]
    if "answer" in item:
        return item["answer"][locale]
    if item["dynamic"] == "day_of_week":
        return _day_of_week_expected(ANSWERED_AT, timezone_name, locale, options)
    return _own_name_expected(PROFILE_NAME, options)


def quick_entries(
    bank: AsturBank,
    *,
    correct_positions: set[int] | None = None,
    over_limit_positions: set[int] = frozenset(),
    elapsed_ms: int = 1500,
    locale: str = "ru",
) -> dict:
    """Stored `lability_answers` shape. `correct_positions=None` → all correct."""
    subtest = bank.subtest("lability")
    entries = {}
    for i, item in enumerate(subtest.items, start=1):
        expected = expected_quick_answer(item, locale=locale)
        wrong = next(o for o in item["options"][locale] if o != expected)
        is_correct = correct_positions is None or i in correct_positions
        entries[str(i)] = {
            "answer": expected if is_correct else wrong,
            "elapsed_ms": elapsed_ms,
            "over_limit": i in over_limit_positions,
            "answered_at": ANSWERED_AT.isoformat(),
        }
    return entries


def attempt_input(bank: AsturBank, answers: dict, lability: dict | None = None, **overrides) -> AttemptInput:
    """A clean, fully timed attempt of a 16-year-old 10th-grader; override
    any field to model a specific protocol."""
    params = dict(
        answers=answers,
        lability_answers=quick_entries(bank) if lability is None else lability,
        subtest_timings_ms={s.key: 60_000 for s in bank.subtests if s.key != "lability"},
        locale="ru",
        profile_name=PROFILE_NAME,
        completed_at=ANSWERED_AT,
        bank_version=1,
        timezone="Asia/Almaty",
        age=16,
        grade=10,
    )
    params.update(overrides)
    return AttemptInput(**params)
