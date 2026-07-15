"""Canonical catalog of the 24 Akinator scoring axes.

Source of truth: akinatorLogic/profi_axes_phase1.md ("ЕДИНСТВЕННЫЙ источник
правды по осям"). Naming convention: short codes (People, Care, Phys, ...),
confirmed with product. Earlier drafts used family-prefixed codes
(A_people, B_analyze, C_body, D_persistence, E_subject_*) — those are
superseded; see the "Изменения от первого черновика" section of that file
for the old -> new mapping. Do not reintroduce the prefixed form.
"""

import enum
from dataclasses import dataclass
from typing import Literal


class AxisFamily(str, enum.Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


@dataclass(frozen=True, slots=True)
class AxisDefinition:
    code: str
    family: AxisFamily
    min_depth: int
    label_ru: str


AXIS_CATALOG: tuple[AxisDefinition, ...] = (
    # A — Ориентация (с чем работаешь). Формат: прямой. Глубина 0-1.
    AxisDefinition("People", AxisFamily.A, 0, "Ориентация на людей, общение"),
    AxisDefinition("Living", AxisFamily.A, 0, "Биология, животные, природа, тело"),
    AxisDefinition("Phys", AxisFamily.A, 0, "Предметы, машины, материалы"),
    AxisDefinition("Data", AxisFamily.A, 0, "Числа, код, количественное"),
    AxisDefinition("Ideas", AxisFamily.A, 0, "Абстрактное, эстетика, замысел"),
    # B — Модальность (что делаешь). Формат: смешанный. Глубина 1-3.
    AxisDefinition("Inv", AxisFamily.B, 1, "Изобретать, придумывать с нуля"),
    AxisDefinition("Obj", AxisFamily.B, 1, "Разбирать/докапываться vs строить инструмент"),
    AxisDefinition("Care", AxisFamily.B, 1, "Лечить, поддерживать конкретного человека"),
    AxisDefinition("Dev", AxisFamily.B, 1, "Учить, растить других"),
    AxisDefinition("Lead", AxisFamily.B, 1, "Вести, организовывать"),
    AxisDefinition("Vis", AxisFamily.B, 1, "Быть на виду, выступать"),
    # C — Канал (через что действуешь). Формат: смешанный. Глубина 3+.
    AxisDefinition("Motor", AxisFamily.C, 3, "Моторика, руки, тело"),
    AxisDefinition("Exp", AxisFamily.C, 3, "Глубокая узкая экспертиза"),
    AxisDefinition("Emp", AxisFamily.C, 3, "Эмоциональный интеллект"),
    # D — Темперамент. Формат: ситуативный, всегда. Глубина 2+.
    AxisDefinition("Focus", AxisFamily.D, 2, "Глубокий длительный фокус"),
    AxisDefinition("Motiv", AxisFamily.D, 2, "Результат, финиш vs процесс"),
    AxisDefinition("Risk", AxisFamily.D, 2, "Комфорт с риском, высокие ставки"),
    AxisDefinition("Auto", AxisFamily.D, 2, "Самостоятельность"),
    AxisDefinition("Struct", AxisFamily.D, 2, "Правила, порядок"),
    AxisDefinition("Pace", AxisFamily.D, 2, "Срочно, динамично"),
    AxisDefinition("Predict", AxisFamily.D, 2, "Новизна, сюрпризы"),
    # E — Практика (факты). Формат: прямой.
    AxisDefinition("Acad", AxisFamily.E, 0, "Готовность к долгой учёбе"),
    AxisDefinition("PhysSt", AxisFamily.E, 0, "Физическая нагрузка"),
    AxisDefinition("Math", AxisFamily.E, 0, "Алгоритмы, высшая математика"),
)

AXIS_CODES: frozenset[str] = frozenset(axis.code for axis in AXIS_CATALOG)

_AXIS_BY_CODE: dict[str, AxisDefinition] = {axis.code: axis for axis in AXIS_CATALOG}

# A, E are always direct; D is always situational; B, C are direct while
# shallow and situational once the question goes deep (see "Правило формата"
# in profi_axes_phase1.md).
_ALWAYS_DIRECT = {AxisFamily.A, AxisFamily.E}
_ALWAYS_SITUATIONAL = {AxisFamily.D}
_MIXED_SITUATIONAL_FROM_DEPTH = 2


def is_valid_axis(code: str) -> bool:
    return code in AXIS_CODES


def format_for_axis(axis_code: str, depth: int) -> Literal["direct", "situational"]:
    axis = _AXIS_BY_CODE.get(axis_code)
    if axis is None:
        raise ValueError(f"Unknown axis code: {axis_code!r}")
    if axis.family in _ALWAYS_DIRECT:
        return "direct"
    if axis.family in _ALWAYS_SITUATIONAL:
        return "situational"
    return "situational" if depth >= _MIXED_SITUATIONAL_FROM_DEPTH else "direct"
