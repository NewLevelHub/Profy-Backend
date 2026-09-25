"""АСТУР attempt lifecycle (PRO-338 Ф3.4 → PRO-427).

Rules:
- at most one `in_progress` attempt per assessment (partial unique index);
- an attempt is opened explicitly (`open_attempt`), which pins its bank
  version AND locale and returns its content in the same response — items
  are never shown before the attempt that will score them exists; a new
  attempt after a completed one needs `retake=True` («Пройти заново»);
- every start/submit names its `run_id`; a payload for another attempt is
  rejected, never re-targeted onto the open one;
- item answers are explicit: answered (value validated against the
  subtest's scoring method) or skipped — a blank value is never an answer;
- re-sending an already accepted subtest with the same payload is a no-op
  (a retried request after a dropped response), a different one is a 409;
- the submit that delivers the last required block finalizes the attempt
  in the same transaction: scored against its pinned version, snapshot
  frozen, status `completed`; a completed attempt is never rescored.
"""
import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import get_locale
from app.i18n.catalog import key as i18n_key
from app.models.assessment import Assessment
from app.models.astur_run import AsturRun, AsturRunStatus
from app.models.profile import Profile
from app.schemas.astur import AttemptHistory
from app.services.astur import timing
from app.services.astur.bank import QUICK_INSTRUCTIONS_KEY, AsturBank, BankSubtest
from app.services.astur.bank_versions import PublishedBank, get_published, latest_published
from app.services.astur.content import build_content
from app.services.astur.scoring import AttemptInput, score_attempt
from app.services.astur.scoring_rules import LEGACY_SCORING_VERSION, ScoringRules, get_rules

ATTEMPT_COMPLETED = "astur_attempt_completed"
RUN_MISMATCH = "astur_run_mismatch"
ALREADY_SUBMITTED = "astur_subtest_already_submitted"
MAX_OPEN_TEXT_LENGTH = 200
# Client-reported time per quick command beyond this multiple of the limit is
# not plausible (a backgrounded tab still reports its real stall).
ELAPSED_MS_LIMIT_FACTOR = 10


def _conflict(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": code, "message": message})


def _unprocessable(detail: object) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


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
        "locale": run.locale,
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


async def open_attempt(
    db: AsyncSession, assessment_id: uuid.UUID, *, user_id: uuid.UUID, retake: bool
) -> dict:
    """Opens (or resumes) the attempt and returns it together with its
    content — bank version and locale are pinned before any item is shown.
    Idempotent while an attempt is open (a double click resumes it)."""
    run = await active_run(db, assessment_id, for_update=True)
    if run is None:
        if await has_completed_run(db, assessment_id) and not retake:
            raise _conflict(ATTEMPT_COMPLETED, "АСТУР attempt is already completed; open a retake explicitly")
        run = await _open_run(db, assessment_id, user_id)
    await db.commit()
    await db.refresh(run)
    published = await get_published(db, run.bank_version_id)
    return {
        "run": await run_summary(db, run),
        "content": build_content(published.bank, bank_version=published.version, run_id=run.id, locale=run.locale),
    }


async def _run_for_write(db: AsyncSession, assessment_id: uuid.UUID, run_id: uuid.UUID) -> AsturRun:
    run = await active_run(db, assessment_id, for_update=True)
    if run is not None and run.id == run_id:
        return run
    claimed = await db.get(AsturRun, run_id)
    if claimed is not None and claimed.assessment_id == assessment_id and claimed.status == AsturRunStatus.completed:
        raise _conflict(ATTEMPT_COMPLETED, "This АСТУР attempt is already completed")
    raise _conflict(RUN_MISMATCH, "The payload is not for this assessment's open АСТУР attempt")


# ── answer validation ───────────────────────────────────────────────────────


def _locale_list(item: dict, field: str, locale: str) -> list:
    value = item.get(field) or {}
    return value.get(locale) or value.get("ru") or []


def _valid_value(subtest: BankSubtest, item: dict, value: object, locale: str) -> bool:
    method = subtest.scoring_method
    if method in ("single_choice", "quick_instruction"):
        return isinstance(value, str) and value in _locale_list(item, "options", locale)
    if method == "pick_pair":
        words = _locale_list(item, "words", locale)
        return (
            isinstance(value, list) and len(value) == 2 and len(set(value)) == 2
            and all(isinstance(w, str) and w in words for w in value)
        )
    if method == "open_text_tiers":
        return isinstance(value, str) and 0 < len(value.strip()) <= MAX_OPEN_TEXT_LENGTH
    if method == "chain_links":
        concepts = _locale_list(item, "concepts", locale)
        return isinstance(value, list) and sorted(value) == sorted(concepts)
    if method == "number_pair":
        return (
            isinstance(value, list) and len(value) == 2
            and all(isinstance(n, int) and not isinstance(n, bool) for n in value)
        )
    return False


def _validate_answers(subtest: BankSubtest, answers: dict, locale: str) -> dict:
    expected = {str(i) for i in range(1, len(subtest.items) + 1)}
    got = set(answers)
    if got != expected:
        raise _unprocessable({
            "detail": i18n_key("api_errors", "astur_item_keys_mismatch", locale="ru").format(field_name="answers"),
            "missing_items": sorted(expected - got, key=int),
            "unexpected_items": sorted(got - expected),
        })
    invalid = [
        key for key, answer in answers.items()
        if answer.status == "answered" and not _valid_value(subtest, subtest.items[int(key) - 1], answer.value, locale)
    ]
    if invalid:
        raise _unprocessable({
            "detail": "answered values do not match the subtest's answer format (send status=skipped for no answer)",
            "invalid_items": sorted(invalid, key=int),
        })
    return {key: answer.model_dump() for key, answer in answers.items()}


# ── start / submit ──────────────────────────────────────────────────────────


def _subtest_or_404(bank: AsturBank, number: int) -> BankSubtest:
    subtest = bank.subtest_by_number(number)
    if subtest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=i18n_key("api_errors", "astur_subtest_not_found", locale="ru").format(n=number),
        )
    return subtest


async def start_subtest(
    db: AsyncSession, assessment_id: uuid.UUID, number: int, *, run_id: uuid.UUID
) -> tuple[AsturRun, str, str]:
    run = await _run_for_write(db, assessment_id, run_id)
    subtest = _subtest_or_404((await get_published(db, run.bank_version_id)).bank, number)
    started_at = dict(run.subtest_started_at)
    timing.start_subtest(started_at, subtest.key)
    run.subtest_started_at = started_at
    await db.commit()
    await db.refresh(run)
    return run, subtest.key, run.subtest_started_at[subtest.key]


def _stored_payload(run: AsturRun, key: str) -> dict | None:
    if key == QUICK_INSTRUCTIONS_KEY:
        if not run.lability_answers:
            return None
        return {k: {"status": v.get("status"), "value": v.get("answer")} for k, v in run.lability_answers.items()}
    return run.answers.get(key)


async def _replay_if_identical(
    db: AsyncSession, assessment_id: uuid.UUID, run_id: uuid.UUID, number: int, answers: dict
) -> tuple[AsturRun, str, None, list[str], bool] | None:
    """A retried submit of the block that already completed the attempt
    (e.g. the response was lost) is answered as a success, not an error."""
    run = await db.get(AsturRun, run_id)
    if run is None or run.assessment_id != assessment_id or run.status != AsturRunStatus.completed:
        return None
    subtest = _subtest_or_404((await get_published(db, run.bank_version_id)).bank, number)
    payload = {k: v.model_dump() for k, v in answers.items()}
    if _stored_payload(run, subtest.key) != payload:
        return None
    return run, subtest.key, None, [], True


async def submit_subtest(
    db: AsyncSession,
    assessment_id: uuid.UUID,
    number: int,
    answers: dict,
    *,
    run_id: uuid.UUID,
    elapsed_ms: dict | None,
    client_timezone: str | None,
) -> tuple[AsturRun, str, int | None, list[str], bool]:
    replay = await _replay_if_identical(db, assessment_id, run_id, number, answers)
    if replay is not None:
        return replay
    run = await _run_for_write(db, assessment_id, run_id)
    published = await get_published(db, run.bank_version_id)
    subtest = _subtest_or_404(published.bank, number)
    is_quick = subtest.key == QUICK_INSTRUCTIONS_KEY
    payload = _validate_answers(subtest, answers, run.locale)

    stored = _stored_payload(run, subtest.key)
    if stored is not None:
        if stored == payload:
            return run, subtest.key, run.subtest_timings_ms.get(subtest.key), [], False
        raise _conflict(ALREADY_SUBMITTED, "This subtest was already submitted in the open attempt")

    limit = published.bank.lability_item_limit_ms
    if is_quick:
        if elapsed_ms is None:
            raise _unprocessable(i18n_key("api_errors", "lability_elapsed_ms_required", locale="ru"))
        if set(elapsed_ms) != set(payload):
            raise _unprocessable(
                i18n_key("api_errors", "astur_item_keys_mismatch", locale="ru").format(field_name="elapsed_ms")
            )
        if any(ms < 0 or ms > limit * ELAPSED_MS_LIMIT_FACTOR for ms in elapsed_ms.values()):
            raise _unprocessable("elapsed_ms values are out of the plausible range")
    elif elapsed_ms is not None:
        raise _unprocessable(i18n_key("api_errors", "elapsed_ms_lability_only", locale="ru"))

    received_at = timing.now_utc()
    actual_ms = timing.elapsed_ms_since_start(run.subtest_started_at, subtest.key, now=received_at)
    run.subtest_started_at = {k: v for k, v in run.subtest_started_at.items() if k != subtest.key}
    if actual_ms is not None:
        run.subtest_timings_ms = {**run.subtest_timings_ms, subtest.key: actual_ms}

    over_limit_items: list[str] = []
    if is_quick:
        stamps = timing.quick_answer_timestamps(elapsed_ms, received_at=received_at)
        over_limit_items = sorted(
            (k for k, ms in elapsed_ms.items() if payload[k]["status"] == "answered" and timing.item_over_limit(ms, limit)),
            key=int,
        )
        run.lability_answers = {
            key: {
                "status": entry["status"],
                "answer": entry["value"],
                "elapsed_ms": elapsed_ms[key],
                "over_limit": key in over_limit_items,
                "answered_at": stamps[key].isoformat(),
            }
            for key, entry in payload.items()
        }
        run.client_timezone = client_timezone
    else:
        run.answers = {**run.answers, subtest.key: payload}

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


async def attempt_history(db: AsyncSession, run: AsturRun, completed_at: datetime) -> AttemptHistory:
    """The respondent's earlier attempts (any assessment): the same form seen
    again means a score change may come from familiarity with the items."""
    earlier = list(
        (
            await db.execute(
                select(AsturRun)
                # `<=`: runs opened in one transaction share created_at.
                .where(AsturRun.user_id == run.user_id, AsturRun.id != run.id, AsturRun.created_at <= run.created_at)
                .order_by(AsturRun.created_at)
            )
        ).scalars()
    )
    exposed = [r for r in earlier if r.answers or r.lability_answers]
    completed = [r for r in earlier if r.status == AsturRunStatus.completed]
    previous_end = max((r.completed_at or r.created_at for r in completed), default=None)
    return AttemptHistory(
        attempt_number=len(completed) + 1,
        repeat_exposure=bool(exposed),
        days_since_previous=(completed_at - previous_end).days if previous_end else None,
    )


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
        history=await attempt_history(db, run, completed_at),
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
