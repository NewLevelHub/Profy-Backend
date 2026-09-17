"""Scoring for АСТУР (PRO-338 Ф3.5): 6 scored subtests + СПН-group + the
"recommended learning profile" (Осведомлённость/Обобщение subject tags) +
lability accuracy-by-half (own metric, excluded from the total score).

Pure functions only — no DB, mirrors `belbin_service.interpret_role_totals`'s
shape (Ф2.5): takes plain dicts (an `AsturRun`'s own `answers`/
`lability_answers` JSONB columns, or any dict shaped like them), returns a
frozen dataclass. Whoever eventually wires this into the report (a future
ticket, same "score first, wire into report later" split this epic has used
throughout — Eysenck Ф1.4/Ф1.5, Belbin Ф2.4/Ф2.5/Ф2.7) assigns the result
onto `AsturRun.raw_score`/`subtest_scores`/`spn_group`/`recommended_profile`/
`lability_*_accuracy` itself; this module never touches the ORM.

Answer-value contract per subtest (deliberately loose typing —
`SubmitAsturSubtestRequest.answers` is `dict[str, Any]`, Ф3.4 — validated
structurally there, interpreted for correctness only here):
  awareness/analogies   -> the exact option text the respondent picked (str)
  classification        -> exactly 2 words (list[str])
  generalization        -> open text (str)
  logical_schemas       -> the respondent's reordered concept list (list[str])
  numeric_series        -> exactly 2 numbers (list[int|str])
Every scorer normalizes text (casefold + collapsed whitespace) before
comparing, and returns 0 for a missing/malformed submission rather than
raising — a partially-answered or garbled item degrades gracefully to "not
credited", never crashes scoring for the other 89 items.
"""
from dataclasses import dataclass
from datetime import datetime

from app.config import AsturThresholds, astur_thresholds
from scripts.astur_bank import (
    ANALOGIES_ITEMS,
    AWARENESS_ITEMS,
    CLASSIFICATION_ITEMS,
    GENERALIZATION_ITEMS,
    LABILITY_ITEMS,
    LOGICAL_SCHEMA_ITEMS,
    NUMERIC_SERIES_ITEMS,
    SUBJECTS,
)


def _normalize(value: object) -> str:
    return " ".join(str(value).strip().casefold().split())


def _score_mc(item: dict, submitted: object) -> int:
    if not isinstance(submitted, str):
        return 0
    return 1 if _normalize(submitted) == _normalize(item["answer"]) else 0


def _score_classification(item: dict, submitted: object) -> int:
    if not isinstance(submitted, list) or len(submitted) != 2:
        return 0
    got = {_normalize(w) for w in submitted}
    expected = {_normalize(w) for w in item["answer"]}
    return 1 if got == expected else 0


def _score_generalization(item: dict, submitted: object) -> int:
    if not isinstance(submitted, str) or not submitted.strip():
        return 0
    norm = _normalize(submitted)
    if norm in {_normalize(s) for s in item["score_2"]}:
        return 2
    if norm in {_normalize(s) for s in item["score_1"]}:
        return 1
    return 0


def _score_logical_schema(item: dict, submitted: object) -> int:
    """1 point per correctly restored ADJACENT link — a pair (concept[i],
    concept[i+1]) counts if those two concepts are adjacent, in that order,
    ANYWHERE in the respondent's submitted sequence, not only at the exact
    original index. A drag-and-drop hierarchy is scored by which
    connections survive, not by absolute position."""
    if not isinstance(submitted, list):
        return 0
    correct = [_normalize(c) for c in item["concepts"]]
    got = [_normalize(c) for c in submitted]
    score = 0
    for i in range(len(correct) - 1):
        a, b = correct[i], correct[i + 1]
        if a in got and b in got and got.index(b) == got.index(a) + 1:
            score += 1
    return score


def _score_numeric_series(item: dict, submitted: object) -> int:
    if not isinstance(submitted, list) or len(submitted) != 2:
        return 0
    try:
        got = [int(x) for x in submitted]
    except (TypeError, ValueError):
        return 0
    return 1 if got == item["answer"] else 0


# geometric_figures (Ф3.1) is deliberately absent here — see
# scripts/astur_bank.py's docstring: folding a new subtest into raw_score
# without recalibrating astur_thresholds.json's SPN-group cut-offs would
# silently shift every existing threshold. It's collected (astur_service
# stores/returns it like any other subtest) but not yet scored.
_SCORERS: dict[str, tuple] = {
    "awareness": (_score_mc, AWARENESS_ITEMS),
    "analogies": (_score_mc, ANALOGIES_ITEMS),
    "classification": (_score_classification, CLASSIFICATION_ITEMS),
    "generalization": (_score_generalization, GENERALIZATION_ITEMS),
    "logical_schemas": (_score_logical_schema, LOGICAL_SCHEMA_ITEMS),
    "numeric_series": (_score_numeric_series, NUMERIC_SERIES_ITEMS),
}

# Ф3.2's own 6 scored subtests: 20+16+12+2*19+26(=sum of len(chain)-1 across
# the 8 logical-schema chains)+15. Self-checked below so a future content
# edit that changes any subtest's size fails loudly here, not silently
# skews СПН-group thresholds (which are pinned to this exact number, see
# app/data/astur_thresholds.json's own comment).
MAX_RAW_SCORE = (
    len(AWARENESS_ITEMS) + len(ANALOGIES_ITEMS) + len(CLASSIFICATION_ITEMS)
    + 2 * len(GENERALIZATION_ITEMS)
    + sum(len(item["concepts"]) - 1 for item in LOGICAL_SCHEMA_ITEMS)
    + len(NUMERIC_SERIES_ITEMS)
)
assert MAX_RAW_SCORE == 127, f"expected MAX_RAW_SCORE 127, got {MAX_RAW_SCORE}"


def score_subtests(answers: dict) -> tuple[dict[str, int], int]:
    """Scores only the subtests actually present in `answers` — a
    partially-completed attempt gets a partial `subtest_scores`/`raw_score`
    rather than being treated as all-zero or raising. `Общий балл` (Ф3.5)
    is meaningful once all 6 scored subtests are present; the caller
    decides whether an attempt is "complete enough" to score (this module
    doesn't gate on that)."""
    subtest_scores: dict[str, int] = {}
    for key, (scorer, items) in _SCORERS.items():
        submitted_map = answers.get(key)
        if not isinstance(submitted_map, dict):
            continue
        subtest_scores[key] = sum(
            scorer(item, submitted_map.get(str(i)))
            for i, item in enumerate(items, start=1)
        )
    return subtest_scores, sum(subtest_scores.values())


def compute_recommended_profile(answers: dict) -> dict:
    """Ф3.5: "по меткам предметной области заданий «Осведомлённость» и
    «Обобщение» считается доля верных ответов в каждой из 3 областей" — a
    SINGLE pooled correct-fraction per subject area across both subtests
    together (awareness items contribute 0/1, generalization items
    contribute their 0/1/2 score halved to the same 0-1 scale), not two
    separate per-subtest sub-scores. `{}` if neither subtest has been
    answered yet."""
    fractions: dict[str, list[float]] = {subject: [] for subject in SUBJECTS}

    awareness_answers = answers.get("awareness")
    if isinstance(awareness_answers, dict):
        for i, item in enumerate(AWARENESS_ITEMS, start=1):
            correct = _score_mc(item, awareness_answers.get(str(i)))
            fractions[item["subject"]].append(float(correct))

    generalization_answers = answers.get("generalization")
    if isinstance(generalization_answers, dict):
        for i, item in enumerate(GENERALIZATION_ITEMS, start=1):
            score = _score_generalization(item, generalization_answers.get(str(i)))
            fractions[item["subject"]].append(score / 2)

    if not any(fractions.values()):
        return {}

    shares = {
        subject: (sum(values) / len(values) if values else 0.0)
        for subject, values in fractions.items()
    }
    return {"recommended": max(shares, key=shares.get), "shares": shares}


# --- Лабильность (own metric, never in raw_score) ---------------------------

_WEEKDAYS_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
_VOWELS_RU = set("аеёиоуыэюя")


def _day_of_week_expected_answer(submitted_at: datetime) -> str:
    weekday = _WEEKDAYS_RU[submitted_at.weekday()]
    return "кружок" if weekday[0] in _VOWELS_RU else "квадрат"


def _own_name_expected_answer(profile_name: str) -> str:
    """Item 6 asks for the first letter of "своего имени" (first name) if
    it's a vowel, else the last letter of "фамилии" (surname) — but
    `Profile.name` (app/models/profile.py) is one combined display-name
    field, not split into first/last. Best-effort heuristic, not exact:
    first word = имя, last word = фамилия — matches typical "Имя Фамилия"
    entry, but is genuinely wrong for a single-word name or a
    surname-first entry. Documented here rather than silently assumed."""
    parts = profile_name.split()
    if not parts:
        return ""
    first_name, last_name = parts[0], parts[-1]
    if first_name and first_name[0].casefold() in _VOWELS_RU:
        return first_name[0]
    return last_name[-1] if last_name else ""


def _is_lability_item_correct(
    index: int, submitted_answer: object, *, submitted_at: datetime, profile_name: str
) -> bool:
    item = LABILITY_ITEMS[index - 1]
    if "answer" in item:
        expected = item["answer"]
    elif item["dynamic"] == "day_of_week":
        expected = _day_of_week_expected_answer(submitted_at)
    elif item["dynamic"] == "own_name":
        expected = _own_name_expected_answer(profile_name)
    else:  # pragma: no cover — astur_bank.py's own assert already guarantees this
        raise AssertionError(f"unknown lability dynamic kind: {item['dynamic']!r}")
    return _normalize(submitted_answer) == _normalize(expected)


def score_lability(
    lability_answers: dict, *, submitted_at: datetime, profile_name: str
) -> tuple[float | None, float | None]:
    """`(None, None)` if lability was never attempted. Otherwise the
    fraction of correct commands in each half of the 8-command block —
    `is_fatigue_signal()` below is the ">25% drop" check Ф3.5 describes."""
    if not lability_answers:
        return None, None

    n = len(LABILITY_ITEMS)
    half = n // 2
    correctness = [
        _is_lability_item_correct(
            i,
            (lability_answers.get(str(i)) or {}).get("answer"),
            submitted_at=submitted_at,
            profile_name=profile_name,
        )
        for i in range(1, n + 1)
    ]
    first_half_accuracy = sum(correctness[:half]) / half
    second_half_accuracy = sum(correctness[half:]) / (n - half)
    return first_half_accuracy, second_half_accuracy


def is_fatigue_signal(first_half_accuracy: float, second_half_accuracy: float) -> bool:
    """Ф3.5: "падение точности более чем на 25% — индикатор умственной
    утомляемости". A rise or a <=25% drop is not flagged."""
    return (first_half_accuracy - second_half_accuracy) > 0.25


@dataclass(frozen=True)
class AsturScoreResult:
    subtest_scores: dict[str, int]
    raw_score: int
    # None only if no scored subtest has been answered yet (score_subtests
    # returned an empty dict) — a threshold lookup on an empty attempt is
    # meaningless, not "worst group".
    spn_group: int | None
    recommended_profile: dict
    lability_first_half_accuracy: float | None
    lability_second_half_accuracy: float | None


def score_run(
    answers: dict,
    lability_answers: dict,
    *,
    submitted_at: datetime,
    profile_name: str,
    thresholds: AsturThresholds = astur_thresholds,
) -> AsturScoreResult:
    subtest_scores, raw_score = score_subtests(answers)
    first_half, second_half = score_lability(
        lability_answers, submitted_at=submitted_at, profile_name=profile_name
    )
    return AsturScoreResult(
        subtest_scores=subtest_scores,
        raw_score=raw_score,
        spn_group=thresholds.spn_group(raw_score) if subtest_scores else None,
        recommended_profile=compute_recommended_profile(answers),
        lability_first_half_accuracy=first_half,
        lability_second_half_accuracy=second_half,
    )
