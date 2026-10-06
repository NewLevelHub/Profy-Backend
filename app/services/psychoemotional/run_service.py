"""Сохранение прохождения психоэмоционального теста (двухфазный контракт).

check-in + circle1 создают строку (`start_run`, §B4 п.1-2 — check-in идёт
первым), circle2 её дополняет (`finish_run`) — между ними проходит вся
основная батарея тестов, а не искусственная пауза. Метрики (PRO-307) и флаг
достоверности (PRO-308) наполняются позже — здесь только §6.1-валидация
входа и запись в append-only историю `psychoemotional_runs`.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.psychoemotional_run import PsychoEmotionalRun
from app.schemas.psychoemotional import (
    FinishPsychoEmotionalRequest,
    StartPsychoEmotionalRequest,
)
from app.services.psychoemotional.constants import CHOICE_COUNT, COLOR_IDS


_PENDING_RUN_INDEX = "uq_psychoemotional_runs_assessment_pending"


class PsychoEmotionalRunAlreadyFinished(Exception):
    """A completed run was retried with a different second-circle payload."""


def _is_pending_run_violation(exc: IntegrityError) -> bool:
    current: BaseException | None = exc
    while current is not None:
        if getattr(current, "constraint_name", None) == _PENDING_RUN_INDEX:
            return True
        diag = getattr(current, "diag", None)
        if getattr(diag, "constraint_name", None) == _PENDING_RUN_INDEX:
            return True
        current = current.__cause__ or current.__context__
    return False


async def get_current_run(
    assessment_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> PsychoEmotionalRun | None:
    """Return the latest run for this assessment, pending or completed."""
    return (
        await db.execute(
            select(PsychoEmotionalRun)
            .where(
                PsychoEmotionalRun.assessment_id == assessment_id,
                PsychoEmotionalRun.user_id == user_id,
            )
            .order_by(PsychoEmotionalRun.created_at.desc(), PsychoEmotionalRun.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _get_pending_run(
    assessment_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> PsychoEmotionalRun | None:
    return (
        await db.execute(
            select(PsychoEmotionalRun)
            .where(
                PsychoEmotionalRun.assessment_id == assessment_id,
                PsychoEmotionalRun.user_id == user_id,
                PsychoEmotionalRun.list2.is_(None),
            )
            .order_by(PsychoEmotionalRun.created_at.desc(), PsychoEmotionalRun.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _is_valid_choice_list(ids: list[int]) -> bool:
    """§6.1: ровно 8 элементов, все уникальны, все ID из {0..7} —
    перестановка восьми цветов."""
    return len(ids) == CHOICE_COUNT and set(ids) == COLOR_IDS


async def start_run(
    assessment_id: uuid.UUID,
    data: StartPsychoEmotionalRequest,
    *,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> PsychoEmotionalRun:
    """check-in + circle1 — перед основной батареей. `list2` заполнится на
    finish; до тех пор строка — «в процессе», движок её не трогает."""
    # A response may be lost after the first request committed. Repeating
    # start must recover that row instead of creating an orphan that the
    # client cannot finish.
    pending = await _get_pending_run(
        assessment_id, user_id=user_id, db=db
    )
    if pending is not None:
        return pending

    run = PsychoEmotionalRun(
        assessment_id=assessment_id,
        user_id=user_id,
        list1=data.list1,
        list1_dt_ms=data.list1_dt_ms,
        checkin=data.checkin,
        tech_invalid=not _is_valid_choice_list(data.list1),
    )
    db.add(run)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if not _is_pending_run_violation(exc):
            raise

        # Two concurrent starts raced past the lookup. The partial unique
        # index selected the winner; both callers receive its stable ID.
        winner = await _get_pending_run(
            assessment_id, user_id=user_id, db=db
        )
        if winner is None:
            raise
        return winner
    await db.refresh(run)
    return run


async def finish_run(
    assessment_id: uuid.UUID,
    run_id: uuid.UUID,
    data: FinishPsychoEmotionalRequest,
    *,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> PsychoEmotionalRun | None:
    """circle2 — в конце всего прохождения. `None` если запись не найдена
    (чужая/не та assessment) или уже завершена ранее (finish — не
    append-only, в отличие от прохождения целиком)."""
    run = (
        await db.execute(
            select(PsychoEmotionalRun)
            .where(
                PsychoEmotionalRun.id == run_id,
                PsychoEmotionalRun.assessment_id == assessment_id,
                PsychoEmotionalRun.user_id == user_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if run is None:
        return None

    if run.list2 is not None:
        if run.list2 == data.list2 and run.list2_dt_ms == data.list2_dt_ms:
            return run
        raise PsychoEmotionalRunAlreadyFinished

    pause_actual_sec = max(
        0, int((datetime.now(timezone.utc) - run.created_at).total_seconds())
    )
    run.list2 = data.list2
    run.list2_dt_ms = data.list2_dt_ms
    run.pause_actual_sec = pause_actual_sec
    run.tech_invalid = run.tech_invalid or not _is_valid_choice_list(data.list2)

    await db.commit()
    await db.refresh(run)
    return run
