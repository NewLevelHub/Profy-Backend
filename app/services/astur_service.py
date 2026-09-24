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

from app.i18n.catalog import key as i18n_key
from app.config import astur_timer_config
from app.i18n import pick_locale, pick_locale_list
from app.models.astur_run import AsturRun
from app.services import subtest_timer
from scripts.astur_bank import SUBTEST_BY_NUMBER, SUBTEST_ITEMS, SUBTESTS

# Which of `_PUBLIC_ITEM_FIELDS`' fields are `{ru,kk}` scalar text vs
# `{ru,kk}` lists vs locale-independent as-is (numeric_series' `sequence`,
# lability's `answer_format` tag) — PRO-338 Ф4.4. Drives `build_content()`'s
# per-field locale resolution below.
_LOCALIZED_SCALAR_FIELDS = {"text", "third", "instruction"}
_LOCALIZED_LIST_FIELDS = {"options", "pair", "words", "concepts"}

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
    "lability": ("instruction", "answer_format", "options"),
    "classification": ("words",),
    "generalization": ("pair",),
    "logical_schemas": ("concepts",),  # shuffled below — see build_content()
    "numeric_series": ("sequence",),
    # No content fields — stimulus is a static frontend image asset
    # addressed by item position, not by anything sent here. Never the
    # item's `answer` letter.
    "geometric_figures": (),
}


def _public_field_value(field: str, value: object) -> object:
    """Resolves one item field to the request's locale — `{ru,kk}` scalar
    text (PRO-338 Ф4.4) via `pick_locale`, `{ru,kk}` lists via
    `pick_locale_list`, everything else (numeric_series' `sequence`,
    lability's `answer_format` tag) passed through as-is, locale-independent."""
    if field in _LOCALIZED_SCALAR_FIELDS:
        return pick_locale(value)
    if field in _LOCALIZED_LIST_FIELDS:
        return pick_locale_list(value)
    return value


def _bank_subtests() -> list[dict]:
    """The hardcoded bank, reshaped into the same bilingual
    subtest/item tree an admin override carries — one function so both
    sources feed `_resolve_subtests` identically (PRO-424)."""
    return [
        {
            "number": n,
            "key": meta["key"],
            "name": meta["name"],
            "instruction": meta["instruction"],
            "item_count": meta["item_count"],
            "scored": meta["scored"],
            "items": SUBTEST_ITEMS[meta["key"]],
        }
        for n, meta in sorted(SUBTEST_BY_NUMBER.items())
    ]


def _resolve_subtests(subtests_bank: list[dict]) -> list[dict]:
    """Runs the request-locale resolution over a bilingual subtests tree —
    the exact same shape whether it came from `_bank_subtests()` or an
    admin override, so a malformed override (missing a locale key, wrong
    field type) fails inside `pick_locale`/`pick_locale_list` the same way
    the bank always would, and the router's fallback catches it the same
    way (PRO-424)."""
    resolved = []
    for subtest in subtests_bank:
        key = subtest["key"]
        public_fields = _PUBLIC_ITEM_FIELDS[key]
        items = []
        for item in subtest["items"]:
            public_item = {field: _public_field_value(field, item.get(field)) for field in public_fields}
            items.append(public_item)
        resolved.append({
            "number": subtest["number"],
            "key": key,
            "name": pick_locale(subtest["name"]),
            "instruction": pick_locale(subtest["instruction"]),
            "item_count": subtest["item_count"],
            "scored": subtest["scored"],
            "time_limit_sec": astur_timer_config.subtest_time_limit_sec.get(key),
            "items": items,
        })
    return resolved


def _shuffle_logical_schemas(content: dict) -> None:
    """`logical_schemas`' `concepts` is the bank's (or override's) correct
    order; this shuffles a COPY per call so the respondent gets a scrambled
    hierarchy to reassemble, never the answer itself — done after locale
    resolution so it applies identically to bank and override content."""
    for subtest in content["subtests"]:
        if subtest["key"] != "logical_schemas":
            continue
        for item in subtest["items"]:
            concepts = item.get("concepts")
            if concepts:
                shuffled = list(concepts)
                random.shuffle(shuffled)
                item["concepts"] = shuffled


async def build_content(db: AsyncSession, ignore_override: bool = False) -> dict:
    """Content for the whole test, potentially overridden by admin.

    `ignore_override` is the fallback path the router takes when a saved
    override doesn't resolve (admin's editor saved an item missing a
    locale) — rather than 500ing for every real test-taker until someone
    fixes the override, it re-renders straight from the bank."""
    subtests_bank = None

    if not ignore_override:
        from app.services.admin_content_service import get_content_override
        from app.i18n import get_locale

        override = await get_content_override(db, "astur")
        if override:
            locale = get_locale()
            override_bank = override.content_ru if locale == "ru" else override.content_kk
            if not override_bank and locale == "kk":
                override_bank = override.content_ru
            if override_bank and override_bank.get("subtests"):
                subtests_bank = override_bank["subtests"]

    if subtests_bank is None:
        subtests_bank = _bank_subtests()

    content = {
        "subtests": _resolve_subtests(subtests_bank),
        "lability_item_limit_ms": astur_timer_config.lability_item_limit_ms,
    }
    _shuffle_logical_schemas(content)
    return content


def _subtest_meta(n: int) -> dict:
    meta = SUBTEST_BY_NUMBER.get(n)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=i18n_key("api_errors", "astur_subtest_not_found", locale="ru").format(n=n),
        )
    return meta


def _validate_item_keys(payload: dict, item_count: int, *, field_name: str) -> None:
    expected = {str(i) for i in range(1, item_count + 1)}
    got = set(payload.keys())
    if got != expected:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "detail": i18n_key("api_errors", "astur_item_keys_mismatch", locale="ru").format(field_name=field_name),
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
        from app.i18n import get_locale
        run = AsturRun(assessment_id=assessment_id, user_id=user_id, locale=get_locale())
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
                detail=i18n_key("api_errors", "lability_elapsed_ms_required", locale="ru"),
            )
        _validate_item_keys(elapsed_ms, item_count, field_name="elapsed_ms")
    elif elapsed_ms is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=i18n_key("api_errors", "elapsed_ms_lability_only", locale="ru"),
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
