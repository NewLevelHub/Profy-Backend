"""Per-item product analytics over completed АСТУР attempts (PRO-427 §6, §8).

Used only to find items that are too easy, confusing or broken for the next
bank version — never presented as a norm. Figures are per bank version (an
item's wording/key is only comparable within one version) and can be cut by
age band / grade at completion. Legacy attempts carry no age, so they only
show up under the "unknown" band.
"""
import statistics
import uuid
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.astur_run import AsturRun, AsturRunStatus
from app.services.astur.bank import QUICK_INSTRUCTIONS_KEY, BankSubtest
from app.services.astur.bank_versions import get_published
from app.services.astur.scoring import normalize

AGE_BANDS = ("under_14", "14_15", "16_17", "18_plus", "unknown")
_TOP_UNRECOGNIZED = 10


def age_band(age: int | None) -> str:
    if age is None:
        return "unknown"
    if age < 14:
        return "under_14"
    if age <= 15:
        return "14_15"
    if age <= 17:
        return "16_17"
    return "18_plus"


def _median(values: list[int]) -> int | None:
    return round(statistics.median(values)) if values else None


def _option_index(item: dict, answer: object, field: str = "options") -> int | None:
    if not isinstance(answer, str):
        return None
    norm = normalize(answer)
    for options in (item.get(field) or {}).values():
        for index, option in enumerate(options):
            if normalize(option) == norm:
                return index
    return None


def _content_item_stats(subtest: BankSubtest, runs: list[AsturRun]) -> list[dict]:
    items = []
    for position, item in enumerate(subtest.items, start=1):
        key = str(position)
        answered = skipped = 0
        earned: list[float] = []
        options: Counter[int] = Counter()
        unrecognized: Counter[str] = Counter()
        max_points = subtest.item_max(item)
        for run in runs:
            value = (run.answers.get(subtest.key) or {}).get(key)
            score = (run.result_snapshot or {}).get("item_scores", {}).get(item["item_id"])
            blank = value is None or (isinstance(value, (str, list)) and not value)
            if blank:
                skipped += 1
            else:
                answered += 1
            if score is not None:
                earned.append(score / max_points)
            if subtest.scoring_method == "single_choice":
                index = _option_index(item, value)
                if index is not None:
                    options[index] += 1
            elif subtest.scoring_method == "open_text_tiers" and not blank and score == 0:
                unrecognized[normalize(value)] += 1
        items.append({
            "item_id": item["item_id"],
            "position": position,
            "attempts": len(runs),
            "answered": answered,
            "skipped": skipped,
            "mean_score_share": round(statistics.fmean(earned), 3) if earned else None,
            "option_counts": [
                {"index": i, "label": label, "count": options[i]}
                for i, label in enumerate((item.get("options") or {}).get("ru", []))
            ],
            "unrecognized_answers": [
                {"text": text, "count": count} for text, count in unrecognized.most_common(_TOP_UNRECOGNIZED)
            ],
            "median_ms": None,
        })
    return items


def _quick_item_stats(subtest: BankSubtest, runs: list[AsturRun]) -> list[dict]:
    items = []
    for position, item in enumerate(subtest.items, start=1):
        key = str(position)
        entries = [run.lability_answers.get(key) for run in runs if run.lability_answers.get(key)]
        options: Counter[int] = Counter(
            i for i in (_option_index(item, e.get("answer")) for e in entries) if i is not None
        )
        on_time = sum(1 for e in entries if not e.get("over_limit"))
        items.append({
            "item_id": item["item_id"],
            "position": position,
            "attempts": len(runs),
            "answered": len(entries),
            "skipped": len(runs) - len(entries),
            "mean_score_share": None,
            "on_time_share": round(on_time / len(entries), 3) if entries else None,
            "option_counts": [
                {"index": i, "label": label, "count": options[i]}
                for i, label in enumerate((item.get("options") or {}).get("ru", []))
            ],
            "unrecognized_answers": [],
            "median_ms": _median([e["elapsed_ms"] for e in entries if isinstance(e.get("elapsed_ms"), int)]),
        })
    return items


async def item_analytics(
    db: AsyncSession, *, bank_version_id: uuid.UUID, band: str | None = None, grade: int | None = None
) -> dict:
    published = await get_published(db, bank_version_id)
    all_runs = list(
        (
            await db.execute(
                select(AsturRun).where(
                    AsturRun.bank_version_id == bank_version_id, AsturRun.status == AsturRunStatus.completed
                )
            )
        ).scalars()
    )

    band_counts: Counter[str] = Counter()
    grade_counts: Counter[int] = Counter()
    runs: list[AsturRun] = []
    for run in all_runs:
        snapshot = run.result_snapshot or {}
        run_band = age_band(snapshot.get("age_at_completion"))
        run_grade = snapshot.get("grade_at_completion")
        band_counts[run_band] += 1
        if run_grade is not None:
            grade_counts[run_grade] += 1
        if (band is None or run_band == band) and (grade is None or run_grade == grade):
            runs.append(run)

    timings: dict[str, list[int]] = defaultdict(list)
    for run in runs:
        for key, ms in run.subtest_timings_ms.items():
            timings[key].append(ms)

    subtests = []
    for subtest in sorted(published.bank.subtests, key=lambda s: s.number):
        stats = (
            _quick_item_stats(subtest, runs)
            if subtest.key == QUICK_INSTRUCTIONS_KEY
            else _content_item_stats(subtest, runs)
        )
        subtests.append({"key": subtest.key, "median_ms": _median(timings[subtest.key]), "items": stats})

    return {
        "bank_version": published.version,
        "attempts": len(runs),
        "filters": {"age_band": band, "grade": grade},
        "age_bands": {b: band_counts[b] for b in AGE_BANDS},
        "grades": dict(sorted(grade_counts.items())),
        "subtests": subtests,
    }
