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


def frustration_index(colors: list[int]) -> dict:
    """Знаки ``!`` основных цветов на позициях 6/7/8 (0–6 баллов)."""
    pos = _positions(colors)
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


def anxiety_index(colors: list[int]) -> dict:
    """Общий показатель тревоги по правилам восьмицветового ряда (0–12).

    В него входят две части: отодвинутые основные цвета (1–4) и выдвинутые
    дополнительные 0/6/7. Фиолетовый (5) может иметь компенсаторное значение,
    но знаками ``!`` не оценивается. Именно эту сумму выводит Psytests.
    """
    frustration = frustration_index(colors)
    compensation = compensation_index(colors)
    breakdown = {
        **frustration["breakdown"],
        **compensation["breakdown"],
    }
    return {
        "score": frustration["score"] + compensation["score"],
        "breakdown": breakdown,
        "frustration_score": frustration["score"],
        "compensation_score": compensation["score"],
        "frustration_breakdown": frustration["breakdown"],
        "compensation_breakdown": compensation["breakdown"],
    }


def _stable_pairs(list1: list[int], list2: list[int]) -> list[frozenset[int]]:
    """Нерасщепившиеся позиционные пары первого выбора."""
    pos2 = _positions(list2)
    return [
        frozenset((left, right))
        for left, right in (list1[0:2], list1[2:4], list1[4:6], list1[6:8])
        if abs(pos2[left] - pos2[right]) == 1
    ]


def _grouped_marks(colors: list[int], stable_pairs: list[frozenset[int]]) -> list[set[str]]:
    """Функции групп МЦВ до поправок на тревогу и компенсацию."""
    by_color = {color: pair for pair in stable_pairs for color in pair}
    groups: list[list[int]] = []
    index = 0
    while index < CHOICE_COUNT:
        color = colors[index]
        pair = by_color.get(color)
        if pair is not None:
            groups.append([color, colors[index + 1]])
            index += 2
            continue

        # Между устойчивыми парами оставшиеся цвета вновь объединяются по
        # два. Именно так во втором выборе образуются, например, ×12 между
        # устойчивой парой +05 и тревожной зоной −37.
        run: list[int] = []
        while index < CHOICE_COUNT and colors[index] not in by_color:
            run.append(colors[index])
            index += 1
        groups.extend(run[offset : offset + 2] for offset in range(0, len(run), 2))

    signs = [SIGN_EQUAL] * len(groups)
    signs[0] = SIGN_PLUS
    if len(groups) > 2:
        signs[1] = SIGN_CROSS
    signs[-1] = SIGN_MINUS

    marks = [set() for _ in colors]
    positions = _positions(colors)
    for group, sign in zip(groups, signs, strict=True):
        for color in group:
            marks[positions[color] - 1].add(sign)

    # Одиночный цвет в зоне ``=`` в МЦВ читается вместе с обоими соседями.
    # Поэтому граница следующей группы может иметь двойную функцию ``=−``.
    for group, sign in zip(groups, signs, strict=True):
        if sign != SIGN_EQUAL or len(group) != 1:
            continue
        position = positions[group[0]] - 1
        if position > 0:
            marks[position - 1].add(SIGN_EQUAL)
        if position + 1 < CHOICE_COUNT:
            marks[position + 1].add(SIGN_EQUAL)
    return marks


def _fixed_marks() -> list[set[str]]:
    return [
        {SIGN_PLUS},
        {SIGN_PLUS},
        {SIGN_CROSS},
        {SIGN_CROSS},
        {SIGN_EQUAL},
        {SIGN_EQUAL},
        {SIGN_MINUS},
        {SIGN_MINUS},
    ]


def _apply_stress_and_compensation(
    colors: list[int], marks: list[set[str]], *, grouped: bool
) -> list[set[str]]:
    """Поправки классической разметки для выдвижения и фрустрации."""
    pos = _positions(colors)
    third_is_compensating = colors[2] in EXTRA_COLOR_IDS
    if third_is_compensating:
        if grouped:
            # При сохранённых парах цвет на третьем месте одновременно
            # участвует в цели-компенсации и в своей исходной группе.
            marks[2].add(SIGN_PLUS)
        else:
            # Без устойчивых пар граница первой функции сдвигается вправо:
            # + + + / × × / = / − −. Так размечен контрольный протокол
            # Psytests 3-1-6-0-5-2-7-4.
            marks = [
                {SIGN_PLUS}, {SIGN_PLUS}, {SIGN_PLUS},
                {SIGN_CROSS}, {SIGN_CROSS}, {SIGN_EQUAL},
                {SIGN_MINUS}, {SIGN_MINUS},
            ]

    frustrated = [pos[color] for color in BASIC_COLOR_IDS if pos[color] >= 6]
    if frustrated:
        stress_start = min(frustrated)
        for index in range(stress_start - 1, CHOICE_COUNT):
            marks[index] = {SIGN_MINUS}
    return marks


def choice_function_marks(list1: list[int], list2: list[int]) -> tuple[list[list[str]], list[list[str]]]:
    """Функциональная разметка обоих выборов.

    Первый ряд размечается позиционно. Для второго учитываются устойчивые
    пары первого ряда; если ни одна пара не сохранилась, используется
    классическая позиционная схема. Затем применяются правила тревоги и
    компенсации.
    """
    stable = _stable_pairs(list1, list2)
    first_base = _grouped_marks(list1, stable) if stable else _fixed_marks()
    second_base = _grouped_marks(list2, stable) if stable else _fixed_marks()
    if stable:
        first_positions = _positions(list1)
        second_positions = _positions(list2)
        for color in COLOR_IDS:
            second_color_marks = second_base[second_positions[color] - 1]
            first_color_marks = first_base[first_positions[color] - 1]
            if (
                SIGN_EQUAL in second_color_marks
                and SIGN_MINUS in second_color_marks
                and SIGN_MINUS in first_color_marks
            ):
                # Общая крайняя пара сохраняет двойную границу ``=−`` в
                # обоих рядах, даже если одиночный ``=`` возник во втором.
                first_color_marks.add(SIGN_EQUAL)
    first = _apply_stress_and_compensation(list1, first_base, grouped=bool(stable))
    second = _apply_stress_and_compensation(list2, second_base, grouped=bool(stable))
    order = (SIGN_PLUS, SIGN_CROSS, SIGN_EQUAL, SIGN_MINUS)
    def serialize(rows: list[set[str]]) -> list[list[str]]:
        return [[sign for sign in order if sign in row] for row in rows]

    return serialize(first), serialize(second)


def choice_analysis(colors: list[int], function_marks: list[list[str]] | None = None) -> dict:
    """Разметка одного из двух цветовых выборов для полного протокола.

    Итоговые индексы по-прежнему считаются по второму, более спонтанному
    выбору.  Но первый ряд нельзя терять: сопоставление двух разметок
    показывает, сохраняются ли тревожные и компенсаторные позиции либо они
    возникли только в одном предъявлении.
    """
    anxiety = anxiety_index(colors)
    compensation = compensation_index(colors)
    return {
        "anxiety": anxiety,
        "compensation": compensation,
        "function_marks": function_marks or [list(mark) for mark in _fixed_marks()],
    }


def functional_groups(list1: list[int], list2: list[int]) -> list[dict]:
    """Группы второго выбора с учётом устойчивых пар первого выбора.

    Пара сохраняется как единая группа, если её цвета вновь стоят рядом
    (порядок внутри пары может поменяться). Расщепившиеся пары показываются
    отдельными цветами. Функциональный знак определяется фактической зоной
    второго ряда; это не меняет классические четыре позиционные пары, а даёт
    отдельный слой анализа устойчивости МЦВ.
    """
    stable_pairs = _stable_pairs(list1, list2)
    stable_pair_by_color = {color: pair for pair in stable_pairs for color in pair}

    groups: list[dict] = []
    used: set[int] = set()
    for color_id in list2:
        if color_id in used:
            continue
        stable_pair = stable_pair_by_color.get(color_id)
        if stable_pair is None:
            colors = [color_id]
            stable = False
        else:
            colors = [candidate for candidate in list2 if candidate in stable_pair]
            stable = True
        used.update(colors)
        groups.append(
            {
                "colors": colors,
                "stable": stable,
            }
        )
    signs = [SIGN_EQUAL] * len(groups)
    signs[0] = SIGN_PLUS
    if len(groups) > 2:
        signs[1] = SIGN_CROSS
    signs[-1] = SIGN_MINUS
    for group, sign in zip(groups, signs, strict=True):
        group["sign"] = sign
    return groups


def functional_combinations(
    list1: list[int],
    list2: list[int],
    *,
    all_rejection_pairs: bool = False,
) -> list[dict]:
    """Все интерпретируемые сочетания второго выбора.

    Внутри каждой функции читаются соседние пары; одиночная зона читается как
    один цвет. Для ``+−`` ведущие цвета сопоставляются с последним цветом.
    Это даёт переменное количество абзацев, как в полном отчёте Psytests.
    """
    _, marks = choice_function_marks(list1, list2)
    stable_pairs = set(_stable_pairs(list1, list2))
    notes: list[dict] = []
    for sign in (SIGN_PLUS, SIGN_CROSS, SIGN_EQUAL, SIGN_MINUS):
        indexes = [index for index, row in enumerate(marks) if sign in row]
        runs: list[list[int]] = []
        for index in indexes:
            if not runs or index != runs[-1][-1] + 1:
                runs.append([index])
            else:
                runs[-1].append(index)
        for run in runs:
            if len(run) == 1:
                colour_groups = [[list2[run[0]]]]
            elif sign == SIGN_MINUS and not all_rejection_pairs:
                # В классическом разделе читается первая тревожная пара.
                # МЦВ дополнительно раскрывает последующие сочетания зоны.
                colour_groups = [[list2[run[0]], list2[run[1]]]]
            else:
                colour_groups = [
                    [list2[left], list2[right]]
                    for left, right in zip(run, run[1:])
                ]
            for colors in colour_groups:
                notes.append(
                    {
                        "sign": sign,
                        "colors": colors,
                        # Устойчива только исходная функциональная пара
                        # первого выбора (1–2 / 3–4 / 5–6 / 7–8), которая
                        # снова оказалась рядом. Простого соседства цветов в
                        # первом ряду недостаточно: позиции 2–3, например,
                        # принадлежат разным функциональным парам.
                        "stable": (
                            len(colors) == 2
                            and frozenset(colors) in stable_pairs
                        ),
                    }
                )

    leading = [
        list2[index]
        for index, row in enumerate(marks)
        if SIGN_PLUS in row and SIGN_CROSS not in row
    ]
    last = list2[-1]
    for color in leading:
        if color != last:
            notes.append({"sign": "plus_minus", "colors": [color, last], "stable": None})
    return notes


def so_standard_score(value: int) -> int:
    """Перевод СО в стандартную 7-балльную шкалу Тимофеева–Филимоненко."""
    if value <= 2:
        return 1
    if value <= 6:
        return 2
    if value <= 12:
        return 3
    if value <= 20:
        return 4
    if value <= 26:
        return 5
    if value <= 30:
        return 6
    return 7


def vk_standard_score(value: float) -> int:
    """Перевод ВК в стандартную 7-балльную шкалу."""
    if value < 0.3:
        return 1
    if value < 0.5:
        return 2
    if value < 0.9:
        return 3
    if value < 1.3:
        return 4
    if value < 2.0:
        return 5
    if value < 3.2:
        return 6
    return 7


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
    # Psytests отбрасывает, а не округляет, второй десятичный знак и
    # стандартный балл определяет по этому отображаемому значению:
    # 9 / 13 = 0.692... → 0.6 → 3.
    return int(numerator * 10 / denominator) / 10


def divergence(list1: list[int], list2: list[int]) -> int:
    """§6.9 — D = Σ|позиция в списке 1 − позиция в списке 2|. 0–32, чётное.
    D = 0 → второй выбор по памяти; D ≥ 20 → ситуативно нестабильно."""
    p1, p2 = _positions(list1), _positions(list2)
    return sum(abs(p1[cid] - p2[cid]) for cid in COLOR_IDS)


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
    so_score: int
    so_level: str
    vk: float
    vk_score: int
    vk_level: str
    d_value: int
    d_memory: bool
    d_situationally_unstable: bool
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
            "so": {"value": self.so, "score": self.so_score, "level": self.so_level},
            "vk": {"value": self.vk, "score": self.vk_score, "level": self.vk_level},
            "d": {
                "value": self.d_value,
                "memory": self.d_memory,
                "situationally_unstable": self.d_situationally_unstable,
            },
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
        so_score=so_standard_score(so),
        so_level=_so_level(so),
        vk=vk,
        vk_score=vk_standard_score(vk),
        vk_level=_vk_level(vk),
        d_value=d_value,
        d_memory=d_value == 0,
        d_situationally_unstable=d_value >= 20,
        thresholds_version=psychoemotional_thresholds.version,
    )
