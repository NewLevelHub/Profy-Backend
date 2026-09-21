"""Флаг достоверности прохождения психоэмоционального теста (МЦВ Собчик), PRO-308.

Пять поведенческих признаков (`psych-block-spec.md §B7`), сводимых в один флаг
`ok` / `caution` / `low` по правилу **0 / 1 / 2+**. Считается ОТДЕЛЬНО от метрик
(`engine.py`, PRO-307) и на них не влияет; прохождение сохраняется и показывается
при любом флаге — не блокируется и не запрашивается повторно (реш. 10).

Δt-признаки берут готовые массивы `list1_dt_ms` / `list2_dt_ms` (пишет
submit-эндпоинт PRO-306), время заново НЕ измеряют. `D` и число расщеплённых пар
переиспользуются из уже посчитанных движком метрик — не пересчитываются здесь.

Пороги — из версионируемого конфига `app/data/psychoemotional_thresholds.json`
(`validity.*`, PRO-305): смена порога = правка JSON + bump `version`, без кода.
"""
from dataclasses import dataclass
from statistics import median

from app.config import psychoemotional_thresholds
from app.models.psychoemotional_run import PsychoEmotionalValidityFlag

# Коды признаков — стабильны (уходят в `psychoemotional_runs.validity_reasons` и в
# секцию отчёта). Порядок = таблица §B7.
REASON_MECHANICAL_PICK = "mechanical_pick"
REASON_TOO_FAST_OVERALL = "too_fast_overall"
REASON_IDENTICAL_LISTS = "identical_lists"
REASON_UNSTABLE_CHOICES = "unstable_choices"
REASON_PAUSE_NOT_HELD = "pause_not_held"

_REASON_ORDER: tuple[str, ...] = (
    REASON_MECHANICAL_PICK,
    REASON_TOO_FAST_OVERALL,
    REASON_IDENTICAL_LISTS,
    REASON_UNSTABLE_CHOICES,
    REASON_PAUSE_NOT_HELD,
)

# «медиана по большинству из 16 кликов» — нужен хотя бы этот объём таймингов,
# иначе скорость выбора не оценивается: отсутствие инструментальных данных ≠
# недостоверное прохождение.
_MIN_TIMING_SAMPLE = 9


@dataclass(frozen=True)
class RunValidity:
    flag: PsychoEmotionalValidityFlag
    reasons: list[str]  # подмножество _REASON_ORDER в фиксированном порядке
    details: dict  # измеренные значения + булевы по каждому из 5 признаков (для калибровки)

    @property
    def flag_value(self) -> str:
        return self.flag.value


def _clean_deltas(*arrays: list) -> list[float]:
    """Плоский список валидных Δt (мс): числа ≥ 0, без bool, None отброшены."""
    out: list[float] = []
    for arr in arrays:
        for d in arr or []:
            if isinstance(d, bool):
                continue
            if isinstance(d, (int, float)) and d >= 0:
                out.append(float(d))
    return out


def evaluate(
    *,
    list1_dt_ms: list,
    list2_dt_ms: list,
    pause_actual_sec: int,
    d_value: int,
    split_count: int,
) -> RunValidity:
    """Посчитать 5 признаков §B7 и свести во флаг. `d_value` / `split_count` —
    уже посчитанные движком (PRO-307) величины, не пересчитываются."""
    t = psychoemotional_thresholds.validity

    deltas = _clean_deltas(list1_dt_ms, list2_dt_ms)
    have_timing = len(deltas) >= _MIN_TIMING_SAMPLE
    median_dt = median(deltas) if deltas else None
    total_active_ms = sum(deltas) if deltas else None

    signs = {
        REASON_MECHANICAL_PICK: bool(
            have_timing and median_dt < t["median_dt_ms_mechanical"]
        ),
        REASON_TOO_FAST_OVERALL: bool(
            have_timing and total_active_ms < t["total_fast_sec"] * 1000
        ),
        REASON_IDENTICAL_LISTS: d_value == 0,
        REASON_UNSTABLE_CHOICES: bool(
            split_count >= t["split_pairs_unstable"] or d_value >= t["d_unstable"]
        ),
        REASON_PAUSE_NOT_HELD: pause_actual_sec < t["pause_min_sec"],
    }
    reasons = [code for code in _REASON_ORDER if signs[code]]

    if not reasons:
        flag = PsychoEmotionalValidityFlag.ok
    elif len(reasons) == 1:
        flag = PsychoEmotionalValidityFlag.caution
    else:
        flag = PsychoEmotionalValidityFlag.low

    return RunValidity(
        flag=flag,
        reasons=reasons,
        details={
            "signs": signs,
            "median_dt_ms": median_dt,
            "total_active_ms": total_active_ms,
            "timing_sample": len(deltas),
            "d_value": d_value,
            "split_count": split_count,
            "pause_actual_sec": pause_actual_sec,
            "thresholds_version": psychoemotional_thresholds.version,
        },
    )
