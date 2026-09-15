"""Психоэмоциональный тест (МЦВ Собчик) — двухфазный контракт.

check-in + circle1 отправляются перед основной батареей тестов (`/start`,
§B4 п.1-2 — check-in идёт первым), circle2 — в конце всего прохождения
(`/{run_id}/finish`). Метрики и флаг достоверности наполняет движок
PRO-307/PRO-308 отдельно."""
import uuid

from pydantic import BaseModel, Field


class StartPsychoEmotionalRequest(BaseModel):
    # Порядок выбора цветов, круг 1 — 8 ID цветов (0–7).
    list1: list[int] = Field(min_length=8, max_length=8)
    # Δt каждого выбора в мс (первый элемент — время до первого выбора).
    list1_dt_ms: list[int] = Field(min_length=8, max_length=8)
    # 3 ответа check-in; пропущенный приходит как «не указано» (§5.2 — фронт).
    checkin: dict[str, str] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class StartPsychoEmotionalResponse(BaseModel):
    run_id: uuid.UUID


class FinishPsychoEmotionalRequest(BaseModel):
    list2: list[int] = Field(min_length=8, max_length=8)
    list2_dt_ms: list[int] = Field(min_length=8, max_length=8)

    model_config = {"extra": "forbid"}


class FinishPsychoEmotionalResponse(BaseModel):
    run_id: uuid.UUID
    # true — list1 или list2 не прошли §6.1 (не перестановка 0–7): сохранён,
    # но не обрабатывается движком.
    tech_invalid: bool
