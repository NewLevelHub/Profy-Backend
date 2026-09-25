"""Scoring of one АСТУР attempt against the bank version it was pinned to
(PRO-427). Pure — no DB, no clock: everything an attempt's result depends
on arrives in `AttemptInput`, and the output is the immutable
`AsturResultSnapshot` persisted at finalize.

Result model:
- every content subtest → `score / max_score` and a 0–100 percent;
- `overall_percent` = plain mean of the percents of the subtests listed in
  the scoring version (equal weight regardless of item count); quick
  instructions are never part of it;
- knowledge profile over subject-tagged items → `leading | mixed |
  insufficient_data` with a leader threshold that scales with area size;
- numeric series shown next to physics/math knowledge, with the gap;
- quick instructions → observed accuracy by halves, on-time only.

Answer-value contract per scoring method (validated structurally at submit,
interpreted only here; malformed/missing values score 0, never raise):
  single_choice    -> the chosen option text (str)
  pick_pair        -> exactly 2 words (list[str])
  open_text_tiers  -> free text (str)
  chain_links      -> the reordered concept list (list[str])
  number_pair      -> exactly 2 numbers (list[int|str])
  quick_instruction-> {"answer": str, "elapsed_ms": int, "over_limit": bool,
                       "answered_at": ISO str | absent on legacy attempts}
"""
import re
import statistics
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.schemas.astur import (
    AsturResultSnapshot,
    MathReasoningResult,
    ProtocolFlag,
    ProtocolQuality,
    QuickInstructionsResult,
    SubjectAreaResult,
    SubjectProfileResult,
    SubtestResult,
)
from app.services.astur.bank import (
    NUMERIC_SERIES_KEY,
    QUICK_INSTRUCTIONS_KEY,
    SUBJECT_TAGGED_KEYS,
    AsturBank,
    BankSubtest,
)
from app.services.astur.scoring_rules import ScoringRules

DEFAULT_TIMEZONE = "Asia/Almaty"
PHYSICS_MATH_SUBJECT = "physics_math"


@dataclass(frozen=True)
class AttemptInput:
    answers: dict
    lability_answers: dict
    subtest_timings_ms: dict
    locale: str
    profile_name: str
    completed_at: datetime
    bank_version: int
    timezone: str | None = None
    age: int | None = None
    grade: int | None = None
    legacy: bool = False


# ── text matching ───────────────────────────────────────────────────────────

# Punctuation is stripped on both sides of every comparison, so it only ever
# loosens matching ("хвойные деревья." == "хвойные деревья").
_PUNCTUATION_RE = re.compile(r"[.,;:!?()\"'«»\-–—]")


def normalize(value: object) -> str:
    text = _PUNCTUATION_RE.sub(" ", str(value))
    return " ".join(text.strip().casefold().split())


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev_row = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr_row = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            curr_row[j] = min(prev_row[j] + 1, curr_row[j - 1] + 1, prev_row[j - 1] + (ca != cb))
        prev_row = curr_row
    return prev_row[-1]


def _word_typo_tolerance(word: str) -> int:
    """<5 chars exact only ("суша"/"душа" are different words), 5–7 chars one
    edit, 8+ chars two edits (keyboard/T9 slip plus autocorrect noise)."""
    n = len(word)
    if n < 5:
        return 0
    return 1 if n <= 7 else 2


def _fuzzy_phrase_match(submitted_norm: str, candidate_norm: str) -> bool:
    submitted_words, candidate_words = submitted_norm.split(), candidate_norm.split()
    if len(submitted_words) != len(candidate_words):
        return False
    return all(
        _levenshtein(sw, cw) <= _word_typo_tolerance(cw) for sw, cw in zip(submitted_words, candidate_words)
    )


def _loc(value: dict, locale: str):
    return value.get(locale) or value["ru"]


# ── per-method item scorers ─────────────────────────────────────────────────


def _score_single_choice(item: dict, submitted: object, locale: str) -> int:
    if not isinstance(submitted, str):
        return 0
    return int(normalize(submitted) == normalize(_loc(item["answer"], locale)))


def _score_pick_pair(item: dict, submitted: object, locale: str) -> int:
    if not isinstance(submitted, list) or len(submitted) != 2:
        return 0
    return int({normalize(w) for w in submitted} == {normalize(w) for w in _loc(item["answer"], locale)})


def _score_open_text(item: dict, submitted: object, locale: str) -> int:
    if not isinstance(submitted, str) or not submitted.strip():
        return 0
    norm = normalize(submitted)
    tier_2 = [normalize(s) for s in _loc(item["score_2"], locale)]
    tier_1 = [normalize(s) for s in _loc(item["score_1"], locale)]
    if norm in tier_2:
        return 2
    if norm in tier_1:
        return 1
    # Typo fallback only after both exact tiers failed — can add credit an
    # exact match would have earned, never take any away.
    if any(_fuzzy_phrase_match(norm, v) for v in tier_2):
        return 2
    if any(_fuzzy_phrase_match(norm, v) for v in tier_1):
        return 1
    return 0


def _score_chain(item: dict, submitted: object, locale: str) -> int:
    """1 point per correctly restored adjacent link, wherever it sits in the
    submitted order — scored by which connections survive, not position."""
    if not isinstance(submitted, list):
        return 0
    correct = [normalize(c) for c in _loc(item["concepts"], locale)]
    got = [normalize(c) for c in submitted]
    return sum(
        1
        for a, b in zip(correct, correct[1:])
        if a in got and b in got and got.index(b) == got.index(a) + 1
    )


def _score_number_pair(item: dict, submitted: object, locale: str) -> int:
    if not isinstance(submitted, list) or len(submitted) != 2:
        return 0
    try:
        return int([int(x) for x in submitted] == item["answer"])
    except (TypeError, ValueError):
        return 0


_ITEM_SCORERS = {
    "single_choice": _score_single_choice,
    "pick_pair": _score_pick_pair,
    "open_text_tiers": _score_open_text,
    "chain_links": _score_chain,
    "number_pair": _score_number_pair,
}


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return not value or all(_is_blank(v) for v in value)
    return False


def _pct(earned: float, maximum: float) -> float:
    return round(earned / maximum * 100, 1) if maximum else 0.0


@dataclass(frozen=True)
class _ScoredItem:
    item_id: str
    subject: str | None
    earned: float
    max_points: int
    answered: bool


def _score_subtest(subtest: BankSubtest, submitted: dict, locale: str) -> list[_ScoredItem]:
    scorer = _ITEM_SCORERS[subtest.scoring_method]
    scored = []
    for position, item in enumerate(subtest.items, start=1):
        value = submitted.get(str(position))
        scored.append(_ScoredItem(
            item_id=item["item_id"],
            subject=item.get("subject"),
            earned=scorer(item, value, locale),
            max_points=subtest.item_max(item),
            answered=not _is_blank(value),
        ))
    return scored


# ── knowledge profile ───────────────────────────────────────────────────────


def _subject_profile(
    bank: AsturBank, scored: dict[str, list[_ScoredItem]], rules: ScoringRules
) -> SubjectProfileResult:
    """Each tagged item contributes its share of its own maximum (0/1 for a
    choice, 0/0.5/1 for a 0–2 open answer), so every area is a percent of its
    own item count and areas of different size compare fairly."""
    earned: dict[str, float] = {s: 0.0 for s in bank.subjects}
    counts: dict[str, int] = {s: 0 for s in bank.subjects}
    answered: dict[str, int] = {s: 0 for s in bank.subjects}
    for key in SUBJECT_TAGGED_KEYS:
        for item in scored.get(key, []):
            if item.subject not in earned:
                continue
            earned[item.subject] += item.earned / item.max_points
            counts[item.subject] += 1
            answered[item.subject] += int(item.answered)

    areas = [
        SubjectAreaResult(
            key=s, earned=round(earned[s], 2), item_count=counts[s],
            answered=answered[s], percent=_pct(earned[s], counts[s]),
        )
        for s in bank.subjects
    ]
    if any(
        a.item_count == 0 or a.answered / a.item_count < rules.profile_min_answered_share for a in areas
    ):
        return SubjectProfileResult(status="insufficient_data", areas=areas)

    leader, runner_up = sorted(areas, key=lambda a: a.percent, reverse=True)[:2]
    smaller_area = min(leader.item_count, runner_up.item_count)
    threshold = max(rules.profile_leading_min_pp, rules.profile_leading_min_items / smaller_area * 100)
    threshold = round(threshold, 1)
    gap = round(leader.percent - runner_up.percent, 1)
    if gap >= threshold:
        return SubjectProfileResult(
            status="leading", leading=leader.key, runner_up=runner_up.key,
            gap_pp=gap, threshold_pp=threshold, areas=areas,
        )
    return SubjectProfileResult(status="mixed", gap_pp=gap, threshold_pp=threshold, areas=areas)


def _math_reasoning(
    subtests: dict[str, SubtestResult], profile: SubjectProfileResult, rules: ScoringRules
) -> MathReasoningResult | None:
    numeric = subtests.get(NUMERIC_SERIES_KEY)
    if numeric is None:
        return None
    knowledge = next((a for a in profile.areas if a.key == PHYSICS_MATH_SUBJECT), None)
    if knowledge is None or profile.status == "insufficient_data":
        return MathReasoningResult(numeric_series_percent=numeric.percent, threshold_pp=rules.math_gap_min_pp)
    gap = round(knowledge.percent - numeric.percent, 1)
    if abs(gap) < rules.math_gap_min_pp:
        divergence = "none"
    else:
        divergence = "knowledge_higher" if gap > 0 else "reasoning_higher"
    return MathReasoningResult(
        numeric_series_percent=numeric.percent,
        physics_math_knowledge_percent=knowledge.percent,
        gap_pp=gap,
        divergence=divergence,
        threshold_pp=rules.math_gap_min_pp,
    )


# ── quick instructions ──────────────────────────────────────────────────────

_WEEKDAYS = {
    "ru": ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"],
    "kk": ["дүйсенбі", "сейсенбі", "сәрсенбі", "бейсенбі", "жұма", "сенбі", "жексенбі"],
}
# The respondent's own name may use either alphabet regardless of the
# interface locale, so the vowel set is the ru+kk union.
_VOWELS = set("аеёиоуыэюя") | set("әіөүұ")
# Profile.name accepts any letters, so a name may be typed in Latin
# ("Arman", "Aigerim"). `y` counts as a vowel: Y-initial names here are
# transliterations of Я/Е/Ю names (Yana, Yerlan, Yulia) — the vowel a child
# thinks of when reading the command. Used only from scoring rules that
# enable it (`own_name_latin_vowels`), so older snapshots stay reproducible.
_LATIN_VOWELS = set("aeiouy")


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def _day_of_week_expected(
    answered_at: datetime, timezone: str | None, locale: str, options: list[str]
) -> str:
    """Options are [circle, square]: circle when today's weekday name — in the
    language the command was read in — starts with a consonant, square
    otherwise, judged on the respondent's local calendar day at the moment
    the command was answered."""
    local = answered_at.astimezone(_zone(timezone))
    weekday = _WEEKDAYS.get(locale, _WEEKDAYS["ru"])[local.weekday()]
    return options[0] if weekday[0] not in _VOWELS else options[1]


def _own_name_expected(profile_name: str, options: list[str], *, latin_vowels: bool = True) -> str:
    """Options are [yes, no]: yes when the first letter of the first name
    (first word of Profile.name — onboarding asks only for the first name)
    is a vowel."""
    parts = profile_name.split()
    if not parts:
        return options[1]
    vowels = _VOWELS | _LATIN_VOWELS if latin_vowels else _VOWELS
    return options[0] if parts[0][0].casefold() in vowels else options[1]


def _quick_item_correct(item: dict, entry: dict, attempt: AttemptInput, rules: ScoringRules) -> bool:
    options = _loc(item["options"], attempt.locale)
    if "answer" in item:
        expected = _loc(item["answer"], attempt.locale)
    elif item["dynamic"] == "day_of_week":
        raw = entry.get("answered_at")
        answered_at = datetime.fromisoformat(raw) if raw else attempt.completed_at
        expected = _day_of_week_expected(answered_at, attempt.timezone, attempt.locale, options)
    else:
        expected = _own_name_expected(
            attempt.profile_name, options, latin_vowels=rules.own_name_latin_vowels
        )
    return normalize(entry.get("answer")) == normalize(expected)


def _quick_instructions(
    subtest: BankSubtest, lability_answers: dict, attempt: AttemptInput, rules: ScoringRules
) -> QuickInstructionsResult:
    n = len(subtest.items)
    half = n // 2
    correct: list[bool] = []
    on_time_flags: list[bool] = []
    times: list[int] = []
    for position, item in enumerate(subtest.items, start=1):
        entry = lability_answers.get(str(position)) or {}
        on_time = bool(entry) and not entry.get("over_limit", False)
        on_time_flags.append(on_time)
        correct.append(on_time and _quick_item_correct(item, entry, attempt, rules))
        if isinstance(entry.get("elapsed_ms"), int):
            times.append(entry["elapsed_ms"])

    on_time = sum(on_time_flags)
    first, second = sum(correct[:half]), sum(correct[half:])
    enough = on_time >= rules.quick_min_on_time
    first_pct = _pct(first, half) if enough else None
    second_pct = _pct(second, n - half) if enough else None
    return QuickInstructionsResult(
        status="ok" if enough else "insufficient_on_time",
        total=n,
        on_time=on_time,
        first_half_correct=first,
        first_half_total=half,
        second_half_correct=second,
        second_half_total=n - half,
        first_half_percent=first_pct,
        second_half_percent=second_pct,
        accuracy_change_pp=round(second_pct - first_pct, 1) if enough else None,
        mean_ms=round(statistics.fmean(times)) if times else None,
        median_ms=round(statistics.median(times)) if times else None,
    )


# ── protocol quality ────────────────────────────────────────────────────────


def _protocol_quality(
    bank: AsturBank,
    subtests: dict[str, SubtestResult],
    quick: QuickInstructionsResult | None,
    attempt: AttemptInput,
    rules: ScoringRules,
) -> ProtocolQuality:
    flags: list[ProtocolFlag] = []
    for subtest in bank.subtests:
        result = subtests.get(subtest.key)
        if result is None:
            continue
        blank = result.item_count - result.answered
        if blank and blank / result.item_count >= rules.blank_share_flag:
            flags.append(ProtocolFlag(code="many_blank_answers", subtest=subtest.key, count=blank))
        actual_ms = attempt.subtest_timings_ms.get(subtest.key)
        if actual_ms is None:
            if not attempt.legacy:
                flags.append(ProtocolFlag(code="subtest_timing_missing", subtest=subtest.key))
        elif subtest.time_limit_sec and actual_ms > (subtest.time_limit_sec + rules.subtest_overtime_grace_sec) * 1000:
            flags.append(ProtocolFlag(code="subtest_over_time", subtest=subtest.key))

    if quick is not None:
        late = quick.total - quick.on_time
        if late:
            flags.append(ProtocolFlag(code="quick_over_limit", subtest=QUICK_INSTRUCTIONS_KEY, count=late))
        if quick.status == "insufficient_on_time":
            flags.append(ProtocolFlag(code="quick_insufficient_on_time", subtest=QUICK_INSTRUCTIONS_KEY))

    if attempt.legacy:
        flags.append(ProtocolFlag(code="legacy_protocol"))
        quick_subtest = bank.subtest(QUICK_INSTRUCTIONS_KEY)
        if quick_subtest and any(item.get("dynamic") == "day_of_week" for item in quick_subtest.items):
            flags.append(ProtocolFlag(code="legacy_day_of_week_estimated", subtest=QUICK_INSTRUCTIONS_KEY))

    blocking = [f for f in flags if f.code != "legacy_protocol"]
    return ProtocolQuality(ok=not blocking, flags=flags)


# ── entry point ─────────────────────────────────────────────────────────────


def score_attempt(bank: AsturBank, attempt: AttemptInput, rules: ScoringRules) -> AsturResultSnapshot:
    scored: dict[str, list[_ScoredItem]] = {}
    subtests: dict[str, SubtestResult] = {}
    for subtest in bank.subtests:
        if subtest.scoring_method == "quick_instruction":
            continue
        submitted = attempt.answers.get(subtest.key)
        if not isinstance(submitted, dict):
            continue
        items = _score_subtest(subtest, submitted, attempt.locale)
        scored[subtest.key] = items
        earned = sum(i.earned for i in items)
        subtests[subtest.key] = SubtestResult(
            key=subtest.key,
            score=earned,
            max_score=subtest.max_score,
            percent=_pct(earned, subtest.max_score),
            item_count=len(items),
            answered=sum(i.answered for i in items),
            in_overall=subtest.key in rules.overall_subtests,
        )

    overall_parts = [r.percent for r in subtests.values() if r.in_overall]
    overall = round(statistics.fmean(overall_parts), 1) if overall_parts else None

    profile = _subject_profile(bank, scored, rules)
    quick_subtest = bank.subtest(QUICK_INSTRUCTIONS_KEY)
    quick = (
        _quick_instructions(quick_subtest, attempt.lability_answers, attempt, rules)
        if quick_subtest is not None and attempt.lability_answers
        else None
    )

    return AsturResultSnapshot(
        scoring_version=rules.version,
        bank_version=attempt.bank_version,
        legacy=attempt.legacy,
        completed_at=attempt.completed_at,
        age_at_completion=attempt.age,
        grade_at_completion=attempt.grade,
        subtests=list(subtests.values()),
        overall_percent=overall,
        subject_profile=profile,
        math_reasoning=_math_reasoning(subtests, profile, rules),
        quick_instructions=quick,
        protocol_quality=_protocol_quality(bank, subtests, quick, attempt, rules),
        item_scores={i.item_id: i.earned for items in scored.values() for i in items},
    )
