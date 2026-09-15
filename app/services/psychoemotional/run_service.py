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
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.psychoemotional_run import PsychoEmotionalRun
from app.schemas.psychoemotional import (
    FinishPsychoEmotionalRequest,
    StartPsychoEmotionalRequest,
)
from app.services.psychoemotional.constants import CHOICE_COUNT, COLOR_IDS


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
    run = PsychoEmotionalRun(
        assessment_id=assessment_id,
        user_id=user_id,
        list1=data.list1,
        list1_dt_ms=data.list1_dt_ms,
        checkin=data.checkin,
        tech_invalid=not _is_valid_choice_list(data.list1),
    )
    db.add(run)
    await db.commit()
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
            select(PsychoEmotionalRun).where(
                PsychoEmotionalRun.id == run_id,
                PsychoEmotionalRun.assessment_id == assessment_id,
                PsychoEmotionalRun.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if run is None or run.list2 is not None:
        return None

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
