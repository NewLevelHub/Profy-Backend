import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AsturRun(Base):
    """Одно завершённое прохождение АСТУР («Характеристики интеллекта»,
    PRO-338 Ф3.3, epic Тикеты-новые-тесты/04-Фаза3-АСТУР.md). Мирроит
    `BelbinRun`/`PsychoEmotionalRun`: **append-only история** —
    `assessment_id` НЕ unique, повторное прохождение = новая строка,
    предыдущие не перезаписываются. Секция отчёта (`IntelligenceSection`,
    Ф3.7) читает последнюю строку по `assessment_id`.

    Per-subtest submit (Ф3.4: `POST /assessment/{id}/astur/subtest/{n}`,
    предпочтён единому сабмиту, чтобы длинный тест не терял прогресс при
    обрыве связи) заполняет `answers`/`subtest_timings_ms` инкрементально,
    один ключ за раз — оба JSONB-словаря `nullable=False, default=dict`
    (тот же принцип, что у `PsychoEmotionalRun.checkin`/`metrics`: всегда
    словарь, пустой до заполнения, а не NULL). Ключи субтестов — латиницей
    (`scripts/astur_bank.py`'s `SUBTESTS[i]["key"]`: awareness/analogies/
    classification/generalization/logical_schemas/numeric_series — 6 сейчас,
    geometric_figures добавится вместе с Ф3.1), форму каждого субтеста
    владеет контент-банк, не эта модель.

    Лабильность (субтест 3) хранится СОВСЕМ отдельно от `answers` — у неё
    другая механика (per-item таймер вместо per-subtest, см. Ф3.4) и не
    входит в общий балл (Ф3.5): `lability_answers` — свои сырые ответы,
    `lability_first_half_accuracy`/`lability_second_half_accuracy` — доля
    верных в первой/второй половине 8 команд, `NULL` пока лабильность не
    посчитана (считает Ф3.5, не сабмит-эндпоинт).

    `raw_score`/`subtest_scores`/`spn_group`/`recommended_profile` — все
    `NULL`/пустые до Ф3.5 (сырое прохождение сохраняет submit-эндпоинт,
    скоринг — отдельный шаг, тот же принцип, что у
    `PsychoEmotionalRun.metrics`/`validity_flag`). `subtest_scores` —
    произвольный JSONB `{subtest_key: балл}` (форму владеет Ф3.5, не эта
    модель — тот же принцип, что у `BelbinRun.role_totals` не перечисляет
    роли жёстко). `recommended_profile` — JSONB `{"recommended": "...",
    "shares": {"humanities": ..., "physics_math": ..., "natural_science":
    ...}}` (форма тоже за Ф3.5) — считается только по меткам предметной
    области субтестов «Осведомлённость»/«Обобщение» (`scripts/astur_bank.py`'s
    `SUBJECTS`), остальные субтесты в него не входят."""

    __tablename__ = "astur_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # NOT unique — append-only история прохождений
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Сырые данные прохождения (наполняет Ф3.4, per-subtest) ---
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    subtest_timings_ms: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # {subtest_key: ISO timestamp} — server-side "started_at" per subtest
    # (Ф3.4's timer engine, `app/services/subtest_timer.py`), written by
    # `POST .../subtest/{n}/start`, read+cleared by the submit endpoint to
    # compute `subtest_timings_ms[key]` from real elapsed server time, never
    # from a client-reported duration. Added alongside Ф3.4, not Ф3.3 —
    # that ticket's own scope was the raw-data/scoring split, not timing.
    subtest_started_at: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # --- Лабильность — отдельная механика и отдельный расчёт (Ф3.4/Ф3.5) ---
    lability_answers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    lability_first_half_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    lability_second_half_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Вычисленные результаты (наполняет скоринг-сервис, Ф3.5) ---
    raw_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subtest_scores: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 1-5 — СПН-группа (доля освоения социально-психологического норматива),
    # NULL пока не посчитана.
    spn_group: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommended_profile: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
