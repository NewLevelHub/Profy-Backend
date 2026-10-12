"""Психоэмоциональный тест (МЦВ Собчик) — двухфазный контракт.

check-in + circle1 отправляются перед основной батареей тестов (`/start`,
§B4 п.1-2 — check-in идёт первым), circle2 — в конце всего прохождения
(`/{run_id}/finish`). Метрики и флаг достоверности наполняет движок
PRO-307/PRO-308 отдельно."""
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field

# ID цвета — 0–7. Повтор или пропуск цвета здесь не отсекается: такой ряд
# сохраняется с tech_invalid (§6.1, run_service), а не отклоняется.
ColorId = Annotated[int, Field(ge=0, le=7)]

# Δt выбора в мс. Ограничена только величина, чтобы в хранимый ряд нельзя было
# записать произвольное число: сутки — срок жизни токена, дольше страница с
# тестом открытой не отправится. Отрицательные значения (часы клиента
# перевели назад) допустимы — движок их отбрасывает (validity._clean_deltas).
_DT_LIMIT_MS = 24 * 60 * 60 * 1000
DeltaMs = Annotated[int, Field(ge=-_DT_LIMIT_MS, le=_DT_LIMIT_MS)]


class CheckIn(BaseModel):
    """3 ответа check-in — закрытые списки, те же, что на экране
    (Profy-Frontend, `shared/config/psychoCheckin.ts`); пропущенный вопрос —
    «не указано» (§5.2).

    Ответы уходят в контекст ИИ-анализа (psych_ai_analysis_context), из
    которого собирается текст для психолога и ученика, — свободный текст
    здесь был бы каналом для инструкций модели."""

    q1: Literal["спокойно", "нормально", "усталость", "напряжение", "раздражение", "не указано"] = "не указано"
    q2: Literal["да", "не совсем", "нет", "не указано"] = "не указано"
    q3: Literal["обычно", "хорошо", "тяжело", "не указано"] = "не указано"

    model_config = {"extra": "forbid"}


class StartPsychoEmotionalRequest(BaseModel):
    # Порядок выбора цветов, круг 1 — 8 ID цветов (0–7).
    list1: list[ColorId] = Field(min_length=8, max_length=8)
    # Δt каждого выбора в мс (первый элемент — время до первого выбора).
    list1_dt_ms: list[DeltaMs] = Field(min_length=8, max_length=8)
    checkin: CheckIn = Field(default_factory=CheckIn)

    model_config = {"extra": "forbid"}


class StartPsychoEmotionalResponse(BaseModel):
    run_id: uuid.UUID


class PsychoEmotionalStateResponse(BaseModel):
    run_id: uuid.UUID | None = None
    status: Literal["not_started", "pending", "completed"]


class FinishPsychoEmotionalRequest(BaseModel):
    list2: list[ColorId] = Field(min_length=8, max_length=8)
    list2_dt_ms: list[DeltaMs] = Field(min_length=8, max_length=8)

    model_config = {"extra": "forbid"}


class FinishPsychoEmotionalResponse(BaseModel):
    run_id: uuid.UUID
    # true — list1 или list2 не прошли §6.1 (не перестановка 0–7): сохранён,
    # но не обрабатывается движком.
    tech_invalid: bool
