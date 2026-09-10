"""Триггер расчёта психоэмоционального теста (PRO-307). Вызывается из
`report_service` при формировании основного отчёта — изолированно: исключение
логируется, отчёт отдаётся. Наполняет ПОСЛЕДНЮЮ строку `psychoemotional_runs`
(metrics + hint_keys + thresholds_version), флаг достоверности прохождения
(`validity_flag` + `validity_reasons`, §B7 / PRO-308) и свод в
`AnalysisResult.psychoemotional`.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult
from app.models.psychoemotional_run import PsychoEmotionalRun
from app.services.psychoemotional import engine, hints, validity


async def _latest_run(
    assessment_id: uuid.UUID, db: AsyncSession
) -> PsychoEmotionalRun | None:
    return (
        await db.execute(
            select(PsychoEmotionalRun)
            .where(PsychoEmotionalRun.assessment_id == assessment_id)
            .order_by(PsychoEmotionalRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def score_and_store(
    assessment_id: uuid.UUID, db: AsyncSession
) -> engine.PsychoEmotionalMetrics | None:
    """Посчитать метрики по последнему прохождению и сохранить. Возвращает
    `None`, если прохождения нет, оно tech-invalid, или уже посчитано."""
    run = await _latest_run(assessment_id, db)
    if run is None or run.tech_invalid or run.metrics:
        return None

    try:
        metrics = engine.compute(list(run.list1), list(run.list2))
    except engine.PsychoEmotionalTechInvalid:
        run.tech_invalid = True
        await db.commit()
        return None

    assembled = hints.assemble(metrics)
    run.metrics = metrics.as_dict()
    run.hint_keys = assembled["hint_keys"]
    run.thresholds_version = metrics.thresholds_version

    # Флаг достоверности прохождения (§B7 / PRO-308) — считается тем же проходом,
    # отдельно от метрик; Δt берутся из сохранённых массивов, D / split-пары —
    # из уже посчитанных метрик, не пересчитываются.
    run_validity = validity.evaluate(
        list1_dt_ms=run.list1_dt_ms or [],
        list2_dt_ms=run.list2_dt_ms or [],
        pause_actual_sec=run.pause_actual_sec,
        d_value=metrics.d_value,
        split_count=metrics.split["split_count"],
    )
    run.validity_flag = run_validity.flag
    run.validity_reasons = run_validity.reasons

    analysis = (
        await db.execute(
            select(AnalysisResult).where(
                AnalysisResult.assessment_id == assessment_id
            )
        )
    ).scalar_one_or_none()
    if analysis is not None:
        analysis.psychoemotional = metrics.container()

    await db.commit()
    return metrics
