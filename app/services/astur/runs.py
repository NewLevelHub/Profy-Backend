"""АСТУР attempt lifecycle (PRO-338 Ф3.4 → PRO-427).

Rules:
- at most one `in_progress` attempt per assessment (partial unique index);
- the very first attempt is opened implicitly by the first start/submit,
  so the main assessment flow needs no extra call; every later attempt
  only via an explicit retake (`start_retake`) — a finished attempt is
  never silently followed by a new one;
- the submit that delivers the last required block finalizes the attempt
  in the same transaction: it is scored against its own pinned bank
  version, the snapshot is frozen, the status flips to `completed`;
- a completed attempt rejects further submits and is never rescored.
"""
import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import get_locale
from app.models.assessment import Assessment
from app.models.astur_run import AsturRun, AsturRunStatus
from app.models.profile import Profile
from app.services.astur import timing
from app.services.astur.bank import QUICK_INSTRUCTIONS_KEY, AsturBank
from app.services.astur.bank_versions import PublishedBank, get_published, latest_published
from app.services.astur.content import build_content
from app.services.astur.scoring import AttemptInput, score_attempt
from app.services.astur.scoring_rules import LEGACY_SCORING_VERSION, ScoringRules, get_rules

ATTEMPT_COMPLETED = "astur_attempt_completed"


# ── queries ─────────────────────────────────────────────────────────────────


async def active_run(db: AsyncSession, assessment_id: uuid.UUID, *, for_update: bool = False) -> AsturRun | None:
    stmt = select(AsturRun).where(
        AsturRun.assessment_id == assessment_id, AsturRun.status == AsturRunStatus.in_progress
    )
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def latest_completed_run(db: AsyncSession, assessment_id: uuid.UUID) -> AsturRun | None:
    return (
        await db.execute(
            select(AsturRun)
            .where(AsturRun.assessment_id == assessment_id, AsturRun.status == AsturRunStatus.completed)
            .order_by(AsturRun.completed_at.desc(), AsturRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def has_completed_run(db: AsyncSession, assessment_id: uuid.UUID) -> bool:
    return bool(
        await db.scalar(
            select(
                exists().where(
                    AsturRun.assessment_id == assessment_id, AsturRun.status == AsturRunStatus.completed
                )
            )
        )
    )


async def _has_any_run(db: AsyncSession, assessment_id: uuid.UUID) -> bool:
    return bool(await db.scalar(select(exists().where(AsturRun.assessment_id == assessment_id))))


def submitted_subtests(run: AsturRun) -> list[str]:
    keys = list(run.answers.keys())
    if run.lability_answers:
        keys.append(QUICK_INSTRUCTIONS_KEY)
    return keys


async def run_summary(db: AsyncSession, run: AsturRun) -> dict:
    bank = await get_published(db, run.bank_version_id)
    return {
        "run_id": run.id,
        "status": run.status.value,
        "bank_version": bank.version,
        "created_at": run.created_at,
        "completed_at": run.completed_at,
        "submitted_subtests": submitted_subtests(run),
    }


async def get_state(db: AsyncSession, assessment_id: uuid.UUID) -> dict:
    active = await active_run(db, assessment_id)
    completed = await latest_completed_run(db, assessment_id)
    if active is not None:
        state = "in_progress"
    elif completed is not None:
        state = "completed"
    else:
        state = "not_started"
    return {
        "status": state,
        "active_run": await run_summary(db, active) if active else None,
        "latest_completed_run": await run_summary(db, completed) if completed else None,
    }


# ── opening attempts ────────────────────────────────────────────────────────


async def _open_run(db: AsyncSession, assessment_id: uuid.UUID, user_id: uuid.UUID) -> AsturRun:
    bank = await latest_published(db)
    run = AsturRun(
        assessment_id=assessment_id,
        user_id=user_id,
        locale=get_locale(),
        status=AsturRunStatus.in_progress,
        bank_version_id=bank.id,
    )
    try:
        async with db.begin_nested():
            db.add(run)
    except IntegrityError:
        # A concurrent request opened the attempt first — use that one.
        existing = await active_run(db, assessment_id, for_update=True)
        if existing is None:
            raise
        return existing
    return run


async def _run_for_write(db: AsyncSession, assessment_id: uuid.UUID, user_id: uuid.UUID) -> AsturRun:
    run = await active_run(db, assessment_id, for_update=True)
    if run is not None:
        return run
    if await _has_any_run(db, assessment_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": ATTEMPT_COMPLETED, "message": "АСТУР attempt is already completed; start a retake"},
        )
    return await _open_run(db, assessment_id, user_id)


async def start_retake(db: AsyncSession, assessment_id: uuid.UUID, *, user_id: uuid.UUID) -> AsturRun:
    """Explicit «Пройти заново». Idempotent while an attempt is open — a
    double click resumes the same attempt rather than opening a second."""
    run = await active_run(db, assessment_id, for_update=True)
    if run is None:
        run = await _open_run(db, assessment_id, user_id)
    await db.commit()
    await db.refresh(run)
    return run


async def content_for(db: AsyncSession, assessment_id: uuid.UUID) -> dict:
    """Content of the bank version the open attempt is pinned to; before the
    first attempt exists, the latest published version (the one a new
    attempt would be pinned to)."""
    run = await active_run(db, assessment_id)
    bank = await get_published(db, run.bank_version_id) if run else await latest_published(db)
    return build_content(bank.bank, bank_version=bank.version, run_id=run.id if run else None)


# ── start / submit ──────────────────────────────────────────────────────────


def _subtest_or_404(bank: AsturBank, number: int):
    subtest = bank.subtest_by_number(number)
    if subtest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No such АСТУР subtest: {number}")
    return subtest


def _validate_item_keys(payload: dict, item_count: int, *, field_name: str) -> None:
    expected = {str(i) for i in range(1, item_count + 1)}
    got = set(payload.keys())
    if got != expected:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "detail": f"{field_name} does not cover exactly this subtest's items",
                "missing_items": sorted(expected - got, key=int),
                "unexpected_items": sorted(got - expected),
            },
        )


async def start_subtest(
    db: AsyncSession, assessment_id: uuid.UUID, number: int, *, user_id: uuid.UUID
) -> tuple[AsturRun, str, str]:
    run = await _run_for_write(db, assessment_id, user_id)
    bank = await get_published(db, run.bank_version_id)
    subtest = _subtest_or_404(bank.bank, number)
    started_at = dict(run.subtest_started_at)
    timing.start_subtest(started_at, subtest.key)
    run.subtest_started_at = started_at
    await db.commit()
    await db.refresh(run)
    return run, subtest.key, run.subtest_started_at[subtest.key]


async def submit_subtest(
    db: AsyncSession,
    assessment_id: uuid.UUID,
    number: int,
    answers: dict,
    *,
    elapsed_ms: dict | None,
    client_timezone: str | None,
    user_id: uuid.UUID,
) -> tuple[AsturRun, str, int | None, list[str], bool]:
    run = await _run_for_write(db, assessment_id, user_id)
    published = await get_published(db, run.bank_version_id)
    subtest = _subtest_or_404(published.bank, number)
    is_quick = subtest.key == QUICK_INSTRUCTIONS_KEY
    item_count = len(subtest.items)

    _validate_item_keys(answers, item_count, field_name="answers")
    if is_quick:
        if elapsed_ms is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="elapsed_ms is required for the quick-instructions subtest",
            )
        _validate_item_keys(elapsed_ms, item_count, field_name="elapsed_ms")
    elif elapsed_ms is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="elapsed_ms is only accepted for the quick-instructions subtest",
        )

    received_at = timing.now_utc()
    actual_ms = timing.elapsed_ms_since_start(run.subtest_started_at, subtest.key, now=received_at)
    started_at = dict(run.subtest_started_at)
    started_at.pop(subtest.key, None)
    run.subtest_started_at = started_at

    over_limit_items: list[str] = []
    if is_quick:
        limit = published.bank.lability_item_limit_ms
        stamps = timing.quick_answer_timestamps(elapsed_ms, received_at=received_at)
        over_limit_items = sorted((k for k, ms in elapsed_ms.items() if timing.item_over_limit(ms, limit)), key=int)
        run.lability_answers = {
            key: {
                "answer": answer,
                "elapsed_ms": elapsed_ms[key],
                "over_limit": key in over_limit_items,
                "answered_at": stamps[key].isoformat(),
            }
            for key, answer in answers.items()
        }
        run.client_timezone = client_timezone
    else:
        run.answers = {**run.answers, subtest.key: answers}
        if actual_ms is not None:
            run.subtest_timings_ms = {**run.subtest_timings_ms, subtest.key: actual_ms}

    completed = set(submitted_subtests(run)) >= published.bank.required_keys
    if completed:
        await _finalize(db, run, published, completed_at=received_at)

    await db.commit()
    await db.refresh(run)
    return run, subtest.key, actual_ms, over_limit_items, completed


# ── finalize ────────────────────────────────────────────────────────────────


async def _profile_for(db: AsyncSession, assessment_id: uuid.UUID) -> Profile | None:
    return (
        await db.execute(
            select(Profile).join(Assessment, Assessment.profile_id == Profile.id).where(Assessment.id == assessment_id)
        )
    ).scalar_one_or_none()


async def build_snapshot(
    db: AsyncSession,
    run: AsturRun,
    published: PublishedBank,
    *,
    rules: ScoringRules,
    completed_at: datetime,
    legacy: bool,
) -> dict:
    profile = await _profile_for(db, run.assessment_id)
    attempt = AttemptInput(
        answers=run.answers,
        lability_answers=run.lability_answers,
        subtest_timings_ms=run.subtest_timings_ms,
        locale=run.locale or "ru",
        profile_name=profile.name if profile else "",
        completed_at=completed_at,
        bank_version=published.version,
        timezone=run.client_timezone,
        # Legacy attempts were finished at an unknown earlier age — never
        # stamp them with today's profile age.
        age=None if legacy else (profile.age if profile else None),
        grade=None if legacy else (profile.grade if profile else None),
        legacy=legacy,
    )
    return score_attempt(published.bank, attempt, rules).model_dump(mode="json")


async def _finalize(db: AsyncSession, run: AsturRun, published: PublishedBank, *, completed_at: datetime) -> None:
    rules = get_rules()
    snapshot = await build_snapshot(db, run, published, rules=rules, completed_at=completed_at, legacy=False)
    run.result_snapshot = snapshot
    run.protocol_quality = snapshot["protocol_quality"]
    run.scoring_version = rules.version
    run.content_hash = published.content_hash
    run.completed_at = completed_at
    run.status = AsturRunStatus.completed


async def freeze_legacy_snapshot(db: AsyncSession, run: AsturRun) -> None:
    """One-time transfer of an attempt completed before PRO-427 into a
    frozen snapshot under the legacy formula (no spatial scale in the
    overall, age unknown, day-of-week command estimated)."""
    published = await get_published(db, run.bank_version_id)
    completed_at = run.completed_at or run.created_at
    snapshot = await build_snapshot(
        db, run, published, rules=get_rules(LEGACY_SCORING_VERSION), completed_at=completed_at, legacy=True
    )
    run.result_snapshot = snapshot
    run.protocol_quality = snapshot["protocol_quality"]
    run.scoring_version = LEGACY_SCORING_VERSION
    run.content_hash = published.content_hash
    run.completed_at = completed_at
