import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PsychoEmotionalValidityFlag(str, enum.Enum):
    """Достоверность прохождения (psych-block-spec.md §B7) — считается
    отдельно от метрик, на них не влияет."""

    ok = "ok"  # 0 признаков
    caution = "caution"  # 1 признак
    low = "low"  # 2+ признаков


class PsychoEmotionalRun(Base):
    """Одно завершённое прохождение психоэмоционального теста (МЦВ Собчик).
    Слово «Люшер» в продукте не используется (PRO-282 §4).

    **Append-only история:** `assessment_id` НЕ unique — повторное
    прохождение = новая строка, предыдущие не перезаписываются (копится
    динамика). Секция `/result` собирается из последней строки
    (report_service._build_psychoemotional_section). Расчёт метрик (PRO-309)
    изолирован от основного отчёта.

    Сырые выборы (`list1`/`list2` — по 8 ID) + тайминги + `metrics` (JSONB,
    форму владеет движок PRO-309: пары +/×/=/− с ( )/[ ], пара +1/−8, индекс
    тревоги + раскладка, компенсация + раскладка + пометка про фиолетовый,
    СО, ВК, D, число расщеплённых, структурные Р/концентричность/
    гетерономность/Ккп) + флаг достоверности прохождения.
    """

    __tablename__ = "psychoemotional_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # NOT unique — история прохождений
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Сырые данные прохождения ---
    list1: Mapped[list] = mapped_column(JSONB, nullable=False)  # 8 ID цветов, порядок выбора круг 1
    list2: Mapped[list] = mapped_column(JSONB, nullable=False)  # 8 ID цветов, круг 2 — все метрики по нему
    list1_dt_ms: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # Δt каждого выбора, круг 1
    list2_dt_ms: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # Δt каждого выбора, круг 2
    pause_actual_sec: Mapped[int] = mapped_column(Integer, nullable=False)  # фактическая длительность паузы
    checkin: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # 3 ответа; «не указано» при пропуске

    # --- Вычисленные метрики (наполняет движок PRO-309; форма — за ним) ---
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # --- Флаг достоверности прохождения (§B7) ---
    # NULL, пока движок (PRO-307/PRO-308) не посчитал: сырое прохождение
    # сохраняет submit-эндпоинт (PRO-306), метрики и флаг наполняются потом.
    validity_flag: Mapped[PsychoEmotionalValidityFlag | None] = mapped_column(
        Enum(PsychoEmotionalValidityFlag, name="psychoemotional_validity_flag_enum"),
        nullable=True,
    )
    validity_reasons: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # NULL до расчёта метрик; тогда же проставляется применённая версия порогов.
    thresholds_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # §6.1: вход не прошёл валидацию (не 8 уникальных ID 0–7) — не обрабатывается,
    # уходит в баг-репорт.
    tech_invalid: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=func.false()
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
