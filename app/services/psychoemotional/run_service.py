"""Сохранение прохождения психоэмоционального теста (PRO-306).

Хранит СЫРОЕ прохождение (2 списка по 8 ID + Δt + пауза + check-in). Метрики
(PRO-307) и флаг достоверности (PRO-308) наполняются позже — здесь только
§6.1-валидация входа и запись в append-only историю `psychoemotional_runs`.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.psychoemotional_run import PsychoEmotionalRun
from app.schemas.psychoemotional import SubmitPsychoEmotionalRequest
from app.services.psychoemotional.constants import CHOICE_COUNT, COLOR_IDS


def _is_valid_choice_list(ids: list[int]) -> bool:
    """§6.1: ровно 8 элементов, все уникальны, все ID из {0..7} —
    перестановка восьми цветов."""
    return len(ids) == CHOICE_COUNT and set(ids) == COLOR_IDS


async def create_run(
    assessment_id: uuid.UUID,
    data: SubmitPsychoEmotionalRequest,
    *,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> PsychoEmotionalRun:
    tech_invalid = not (
        _is_valid_choice_list(data.list1) and _is_valid_choice_list(data.list2)
    )
    run = PsychoEmotionalRun(
        assessment_id=assessment_id,
        user_id=user_id,
        list1=data.list1,
        list2=data.list2,
        list1_dt_ms=data.list1_dt_ms,
        list2_dt_ms=data.list2_dt_ms,
        pause_actual_sec=data.pause_actual_sec,
        checkin=data.checkin,
        tech_invalid=tech_invalid,
        # metrics {} / validity_flag NULL / thresholds_version NULL —
        # наполняет движок PRO-307/PRO-308.
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run
