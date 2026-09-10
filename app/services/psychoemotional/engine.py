"""Движок метрик психоэмоционального теста (МЦВ Собчик), PRO-307.

Все клинические метрики считаются **по списку 2**; список 1 — только для
устойчивых/расщеплённых пар (§6.3) и расхождения D (§6.9). Формулы —
`тестЛюшера.md §6` / `psych-block-spec.md §B5`; уровни — из версионируемого
конфига (`app/data/psychoemotional_thresholds.json`, PRO-305).

Позиция цвета = его ранг в списке, целое 1–8 (1 = первый, самый приятный
выбор). ID цвета (0–7) ≠ позиция.
"""
from dataclasses import dataclass, field

from app.config import psychoemotional_thresholds
from app.services.psychoemotional.constants import (
    AUTOGENIC_NORM_POSITION,
    BASIC_COLOR_IDS,
    BORDER_COLOR_ID,
    CHOICE_COUNT,
    COLOR_IDS,
    EXTRA_COLOR_IDS,
)

# Читаемые имена ID (§B2)
_BLUE, _GREEN, _RED, _YELLOW, _BLACK = 1, 2, 3, 4, 7

# Знаки позиционных пар (§6.2). ASCII-имена — совпадают с ключами каталога
# подсказок (`fn.<sign>.<colorId>`).
SIGN_PLUS = "plus"  # позиции 1–2: цель
SIGN_CROSS = "cross"  # позиции 3–4: актуальное состояние
SIGN_EQUAL = "equal"  # позиции 5–6: зона безразличия
SIGN_MINUS = "minus"  # позиции 7–8: отвергаемое, скрытое напряжение


class PsychoEmotionalTechInvalid(ValueError):
    """§6.1 — вход не перестановка восьми цветов; не обрабатывается."""


def is_valid_list(colors: list[int]) -> bool:
    return len(colors) == CHOICE_COUNT and set(colors) == COLOR_IDS


def _positions(colors: list[int]) -> dict[int, int]:
    """color_id -> ранг 1..8."""
    return {color_id: rank for rank, color_id in enumerate(colors, start=1)}


# --- отдельные метрики -----------------------------------------------------
def positional_pairs(list2: list[int]) -> dict:
    """§6.2 — пары по позициям + корневой конфликт +1/−8."""
    return {
        SIGN_PLUS: list2[0:2],
        SIGN_CROSS: list2[2:4],
        SIGN_EQUAL: list2[4:6],
        SIGN_MINUS: list2[6:8],
        "root_conflict": [list2[0], list2[7]],
    }


def split_pairs(list1: list[int], list2: list[int]) -> dict:
    """§6.3 — 4 функциональные пары из списка 1; рядом в списке 2 → устойчива
    `( )`, разошлись → расщеплена `[ ]`. ≥ 3 расщеплённых → нестабильность."""
    pos2 = _positions(list2)
    pairs1 = [list1[0:2], list1[2:4], list1[4:6], list1[6:8]]
    detail = []
    split_count = 0
    for a, b in pairs1:
        stable = abs(pos2[a] - pos2[b]) == 1
        detail.append({"colors": [a, b], "stable": stable})
        if not stable:
            split_count += 1
    return {
        "pairs": detail,
        "split_count": split_count,
        "instability": split_count >= 3,
    }


_ANXIETY_BY_POSITION = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 1, 7: 2, 8: 3}


def anxiety_index(list2: list[int]) -> dict:
    """§6.4 — по основным цветам (1–4), позиции 6/7/8 фрустрации. Сумма 0–12."""
    pos = _positions(list2)
    breakdown = {cid: _ANXIETY_BY_POSITION[pos[cid]] for cid in BASIC_COLOR_IDS}
    return {"score": sum(breakdown.values()), "breakdown": breakdown}


_COMPENSATION_BY_POSITION = {1: 3, 2: 2, 3: 1}  # позиции 4–8 → 0


def compensation_index(list2: list[int]) -> dict:
    """§6.5 — по дополнительным цветам (0, 6, 7), позиции 1/2/3 выдвижения.
    Сумма 0–9. Фиолетовый (5) в подсчёт НЕ входит — только пометка, если он
    на позициях 1–3."""
    pos = _positions(list2)
    breakdown = {
        cid: _COMPENSATION_BY_POSITION.get(pos[cid], 0) for cid in EXTRA_COLOR_IDS
    }
    purple_pos = pos[BORDER_COLOR_ID]
    return {
        "score": sum(breakdown.values()),
        "breakdown": breakdown,
        "purple_forward": purple_pos <= 3,
        "purple_position": purple_pos,
    }


def so_deviation(list2: list[int]) -> int:
    """§6.6 — СО = Σ|позиция в списке 2 − позиция в аутогенной норме|,
    норма `3,4,2,5,1,6,0,7`. Диапазон 0–32, всегда чётное."""
    pos2 = _positions(list2)
    return sum(abs(pos2[cid] - AUTOGENIC_NORM_POSITION[cid]) for cid in COLOR_IDS)


def vegetative_coefficient(list2: list[int]) -> float:
    """§6.7 — ВК = (18 − поз.кр − поз.жёлт) / (18 − поз.син − поз.зел).
    Делитель ∈ [3, 15] — деление на ноль невозможно. Диапазон 0.2–5.0."""
    pos = _positions(list2)
    numerator = 18 - pos[_RED] - pos[_YELLOW]
    denominator = 18 - pos[_BLUE] - pos[_GREEN]
    return round(numerator / denominator, 2)


def divergence(list1: list[int], list2: list[int]) -> int:
    """§6.9 — D = Σ|позиция в списке 1 − позиция в списке 2|. 0–32, чётное.
    D = 0 → второй выбор по памяти; D ≥ 20 → ситуативно нестабильно."""
    p1, p2 = _positions(list1), _positions(list2)
    return sum(abs(p1[cid] - p2[cid]) for cid in COLOR_IDS)


def structural_indices(list2: list[int]) -> dict:
    """§6.8 — вспомогательные, БЕЗ зон нормы. Позиция = ранг 1–8."""
    pos = _positions(list2)
    return {
        # Р: меньше сумма → выше работоспособность (диапазон 6–21)
        "performance": pos[_GREEN] + pos[_RED] + pos[_YELLOW],
        "concentricity": (pos[_BLUE] + pos[_GREEN]) - (pos[_RED] + pos[_YELLOW]),
        "heteronomy": (pos[_BLUE] + pos[_YELLOW]) - (pos[_GREEN] + pos[_RED]),
        "kkp": round(pos[_BLACK] / (pos[_BLUE] + pos[_GREEN]), 3),
    }


# --- уровни по конфигу v1 ------------------------------------------------
def _so_level(so: int) -> str:
    t = psychoemotional_thresholds.so
    if so <= t["norm_max"]:
        return "norm"
    if so <= t["elevated_max"]:
        return "elevated"
    return "high"


def _anxiety_level(score: int) -> str:
    t = psychoemotional_thresholds.anxiety
    if score <= t["low_max"]:
        return "low"
    if score <= t["moderate_max"]:
        return "moderate"
    if score <= t["high_max"]:
        return "high"
    return "very_high"


def _compensation_level(score: int) -> str:
    t = psychoemotional_thresholds.compensation
    if score <= t["low_max"]:
        return "low"
    if score <= t["moderate_max"]:
        return "moderate"
    return "high"


def _vk_level(vk: float) -> str:
    t = psychoemotional_thresholds.vk
    if vk < t["low_tone_max"]:
        return "low_tone"
    if vk <= t["reduced_max"]:
        return "reduced"
    if vk <= t["balance_max"]:
        return "balance"
    return "overexcited"


@dataclass(frozen=True)
class PsychoEmotionalMetrics:
    list1: list[int]
    list2: list[int]
    pairs: dict
    split: dict
    anxiety: dict
    compensation: dict
    so: int
    so_level: str
    vk: float
    vk_level: str
    d_value: int
    d_memory: bool
    d_situationally_unstable: bool
    structural: dict
    thresholds_version: int
    anxiety_level: str = field(default="")
    compensation_level: str = field(default="")

    def as_dict(self) -> dict:
        """Полная раскладка — в `psychoemotional_runs.metrics`."""
        return {
            "pairs": self.pairs,
            "split": self.split,
            "anxiety": {**self.anxiety, "level": self.anxiety_level},
            "compensation": {**self.compensation, "level": self.compensation_level},
            "so": {"value": self.so, "level": self.so_level},
            "vk": {"value": self.vk, "level": self.vk_level},
            "d": {
                "value": self.d_value,
                "memory": self.d_memory,
                "situationally_unstable": self.d_situationally_unstable,
            },
            "structural": self.structural,
            "thresholds_version": self.thresholds_version,
        }

    def container(self) -> dict:
        """Компактный свод — в `AnalysisResult.psychoemotional` (для PRO-309)."""
        return {
            "so": self.so,
            "so_level": self.so_level,
            "anxiety_score": self.anxiety["score"],
            "anxiety_level": self.anxiety_level,
            "compensation_score": self.compensation["score"],
            "compensation_level": self.compensation_level,
            "vk": self.vk,
            "vk_level": self.vk_level,
            "d_value": self.d_value,
            "split_pairs": self.split["split_count"],
            "instability": self.split["instability"],
            "thresholds_version": self.thresholds_version,
        }


def compute(list1: list[int], list2: list[int]) -> PsychoEmotionalMetrics:
    """Посчитать все метрики. Бросает `PsychoEmotionalTechInvalid`, если вход
    не прошёл §6.1 (вызывающий уже проставил `tech_invalid` на строке)."""
    if not (is_valid_list(list1) and is_valid_list(list2)):
        raise PsychoEmotionalTechInvalid("§6.1: lists must be a permutation of 0..7")

    anxiety = anxiety_index(list2)
    compensation = compensation_index(list2)
    so = so_deviation(list2)
    vk = vegetative_coefficient(list2)
    d_value = divergence(list1, list2)

    return PsychoEmotionalMetrics(
        list1=list1,
        list2=list2,
        pairs=positional_pairs(list2),
        split=split_pairs(list1, list2),
        anxiety=anxiety,
        anxiety_level=_anxiety_level(anxiety["score"]),
        compensation=compensation,
        compensation_level=_compensation_level(compensation["score"]),
        so=so,
        so_level=_so_level(so),
        vk=vk,
        vk_level=_vk_level(vk),
        d_value=d_value,
        d_memory=d_value == 0,
        d_situationally_unstable=d_value >= 20,
        structural=structural_indices(list2),
        thresholds_version=psychoemotional_thresholds.version,
    )
