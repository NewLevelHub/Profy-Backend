"""Per-subtest submit for АСТУР (PRO-338 Ф3.4).

One `AsturRun` row per ATTEMPT (append-only across attempts, per Ф3.3), but
built up incrementally across up to 7 per-subtest requests within one
attempt — the opposite resubmit philosophy from Belbin (Ф2.4, where every
submit is a brand-new row): here, "resubmit" while an attempt is still
incomplete means "continue the same attempt after a dropped connection",
not "start over". A submit only starts a NEW row when the latest one for
this assessment is already complete (every scored subtest + lability
present) — so a genuine retake still gets its own fresh append-only row,
matching astur_runs' own append-only contract (Ф3.3)."""
import random
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import astur_timer_config
from app.models.astur_run import AsturRun
from app.services import subtest_timer
from scripts.astur_bank import SUBTEST_BY_NUMBER, SUBTEST_ITEMS, SUBTESTS

_SCORED_KEYS = {s["key"] for s in SUBTESTS if s["scored"]}
_LABILITY_KEY = "lability"
_LABILITY_ITEM_KEYS = {str(i) for i in range(1, len(SUBTEST_ITEMS[_LABILITY_KEY]) + 1)}

# Per-subtest fields safe to hand to the respondent — everything else
# (answer/score_2/score_1/score_0_example/dynamic/note/rule/subject) is a
# scoring key or reviewer-only note, never sent over the wire (Ф3.6
# prerequisite: same non-disclosure principle as every other scored
# instrument in this epic).
_PUBLIC_ITEM_FIELDS: dict[str, tuple[str, ...]] = {
    "awareness": ("text", "options"),
    "analogies": ("pair", "third", "options"),
    "lability": ("instruction", "answer_format"),
    "classification": ("words",),
    "generalization": ("pair",),
    "logical_schemas": ("concepts",),  # shuffled below — see build_content()
    "numeric_series": ("sequence",),
}


def build_content() -> dict:
    """Static content for the whole test — same for every user, no DB
    access. `logical_schemas`' `concepts` is the bank's correct order; this
    shuffles a COPY per call so the respondent gets a scrambled hierarchy
    to reassemble, never the answer itself."""
    subtests = []
    for n, meta in sorted(SUBTEST_BY_NUMBER.items()):
        key = meta["key"]
        public_fields = _PUBLIC_ITEM_FIELDS[key]
        items = []
        for item in SUBTEST_ITEMS[key]:
            public_item = {field: item[field] for field in public_fields}
            if key == "logical_schemas":
                shuffled = list(public_item["concepts"])
                random.shuffle(shuffled)
                public_item["concepts"] = shuffled
            items.append(public_item)
        subtests.append({
            "number": n,
            "key": key,
            "name": meta["name"],
            "instruction": meta["instruction"],
            "item_count": meta["item_count"],
            "scored": meta["scored"],
            "time_limit_sec": astur_timer_config.subtest_time_limit_sec.get(key),
            "items": items,
        })
    return {
        "subtests": subtests,
        "lability_item_limit_ms": astur_timer_config.lability_item_limit_ms,
    }


def _subtest_meta(n: int) -> dict:
    meta = SUBTEST_BY_NUMBER.get(n)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No such АСТУР subtest: {n}",
        )
    return meta


def _validate_item_keys(payload: dict, item_count: int, *, field_name: str) -> None:
    expected = {str(i) for i in range(1, item_count + 1)}
    got = set(payload.keys())
    if got != expected:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "detail": f"{field_name} does not cover exactly this subtest's items",
                "missing_items": sorted(expected - got),
                "unexpected_items": sorted(got - expected),
            },
        )


def is_complete(run: AsturRun) -> bool:
    """Public — reused by extended_block_service (post-Ф4.1 follow-up) to
    tell the student-facing assignment list "in progress" from "done": an
    `AsturRun` row existing is NOT the same as complete here, unlike Belbin
    (one-shot submit) — per-subtest submission means a row can exist with
    only some of the 7 subtests answered."""
    if not _SCORED_KEYS.issubset(run.answers.keys()):
        return False
    return _LABILITY_ITEM_KEYS.issubset(run.lability_answers.keys())


async def _latest_run(assessment_id: uuid.UUID, db: AsyncSession) -> AsturRun | None:
    return (
        await db.execute(
            select(AsturRun)
            .where(AsturRun.assessment_id == assessment_id)
            .order_by(AsturRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def get_latest_run(assessment_id: uuid.UUID, db: AsyncSession) -> AsturRun | None:
    """Public wrapper around `_latest_run` for callers outside this module
    (Ф3.7's report builder) — same "latest by created_at" append-only-
    history convention as `belbin_service.get_latest_run`. `None` if АСТУР
    was never assigned/completed for this assessment (a normal, common
    case — optional psychologist-assigned block, not part of the main
    battery)."""
    return await _latest_run(assessment_id, db)


async def _get_or_create_active_run(
    assessment_id: uuid.UUID, *, user_id: uuid.UUID, db: AsyncSession
) -> AsturRun:
    run = await _latest_run(assessment_id, db)
    if run is None or is_complete(run):
        run = AsturRun(assessment_id=assessment_id, user_id=user_id)
        db.add(run)
        await db.flush()
    return run


async def start_subtest(
    assessment_id: uuid.UUID, n: int, *, user_id: uuid.UUID, db: AsyncSession
) -> tuple[AsturRun, str, str]:
    meta = _subtest_meta(n)
    run = await _get_or_create_active_run(assessment_id, user_id=user_id, db=db)

    started_at = dict(run.subtest_started_at)
    subtest_timer.start_subtest(started_at, meta["key"])
    run.subtest_started_at = started_at  # reassign — JSONB mutation tracking needs a new object

    await db.commit()
    await db.refresh(run)
    return run, meta["key"], run.subtest_started_at[meta["key"]]


async def submit_subtest(
    assessment_id: uuid.UUID,
    n: int,
    answers: dict,
    elapsed_ms: dict | None,
    *,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[AsturRun, str, int | None, list[str]]:
    meta = _subtest_meta(n)
    key = meta["key"]
    item_count = meta["item_count"]
    is_lability = key == _LABILITY_KEY

    _validate_item_keys(answers, item_count, field_name="answers")
    if is_lability:
        if elapsed_ms is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="elapsed_ms is required for the lability subtest",
            )
        _validate_item_keys(elapsed_ms, item_count, field_name="elapsed_ms")
    elif elapsed_ms is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="elapsed_ms is only accepted for the lability subtest",
        )

    run = await _get_or_create_active_run(assessment_id, user_id=user_id, db=db)

    actual_ms = subtest_timer.elapsed_ms_since_start(run.subtest_started_at, key)
    started_at = dict(run.subtest_started_at)
    started_at.pop(key, None)
    run.subtest_started_at = started_at

    over_limit_items: list[str] = []
    if is_lability:
        over_limit_items = sorted(
            (item_id for item_id, ms in elapsed_ms.items() if subtest_timer.item_over_limit(ms)),
            key=int,
        )
        lability_answers = dict(run.lability_answers)
        for item_id, answer in answers.items():
            lability_answers[item_id] = {
                "answer": answer,
                "elapsed_ms": elapsed_ms[item_id],
                "over_limit": item_id in over_limit_items,
            }
        run.lability_answers = lability_answers
    else:
        run_answers = dict(run.answers)
        run_answers[key] = answers
        run.answers = run_answers
        if actual_ms is not None:
            timings = dict(run.subtest_timings_ms)
            timings[key] = actual_ms
            run.subtest_timings_ms = timings

    await db.commit()
    await db.refresh(run)
    return run, key, actual_ms, over_limit_items
