"""Психоэмоциональный тест (МЦВ Собчик) — контракт submit-эндпоинта (PRO-306).
Фронт присылает сырое прохождение; метрики и флаг достоверности наполняет
движок PRO-307/PRO-308."""
import uuid

from pydantic import BaseModel, Field


class SubmitPsychoEmotionalRequest(BaseModel):
    # Порядок выбора цветов, круг 1 и круг 2 — по 8 ID цветов (0–7).
    list1: list[int] = Field(min_length=8, max_length=8)
    list2: list[int] = Field(min_length=8, max_length=8)
    # Δt каждого выбора в мс (первый элемент — время до первого выбора).
    list1_dt_ms: list[int] = Field(min_length=8, max_length=8)
    list2_dt_ms: list[int] = Field(min_length=8, max_length=8)
    # Фактическая длительность паузы (§5.4 — фиксируется, не в скоринге).
    pause_actual_sec: int = Field(ge=0)
    # 3 ответа check-in; пропущенный приходит как «не указано» (§5.2 — фронт).
    checkin: dict[str, str] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class SubmitPsychoEmotionalResponse(BaseModel):
    run_id: uuid.UUID
    # true — вход не прошёл §6.1 (не перестановка 0–7): сохранён, но не
    # обрабатывается движком.
    tech_invalid: bool
