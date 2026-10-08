"""Текстовое толкование психоэмоционального теста для специалиста (PRO-448).

Никакой генерации ИИ: метрики прохождения (`PsychoEmotionalMetrics.as_dict()`,
по списку 2) → ключи статического каталога
`app/i18n/catalog/psychoemotional_interpretation.py` → текст на языке запроса.

Порядок чтения (`psychoemotional-templates.md §8`):
  reading     — нестабильность прохождения: задаёт рамку доверия к остальному;
  highlights  — связка −X/+Y, тревога по основным цветам, компенсация
                дополнительными; сильные сигналы первыми;
  indices     — абзац к уровню тревоги / СО / ВК;
  positions   — пара цветов каждой функциональной группы (+ × = −) и
                главное противоречие: первый цвет против последнего.
Связка заменяет отдельные тексты про оба своих цвета. Тексты пар написаны в
тоне «старается / возможно», поэтому рядом с высокой тревогой не читаются как
«всё хорошо» и отдельного подавления не требуют.
"""
from app.i18n.catalog import tr
from app.schemas.result_v2 import (
    PsychoEmotionalHighlight,
    PsychoEmotionalIndexNote,
    PsychoEmotionalInterpretation,
    PsychoEmotionalMcvGroup,
    PsychoEmotionalPositionNote,
)
from app.services.psychoemotional.constants import BASIC_COLOR_IDS, BORDER_COLOR_ID, EXTRA_COLOR_IDS
from app.services.psychoemotional.engine import (
    SIGN_MINUS,
    SIGN_PLUS,
    functional_combinations,
)


def _first_at(color_ids: tuple[int, ...], pos: dict[int, int], positions: tuple[int, ...]) -> int | None:
    """Цвет из `color_ids` на первой из `positions`, где он есть (8 раньше 7 и т. п.)."""
    for position in positions:
        for color_id in color_ids:
            if pos[color_id] == position:
                return color_id
    return None


def _highlights(pos: dict[int, int], texts: dict) -> list[PsychoEmotionalHighlight]:
    frustrated = _first_at(BASIC_COLOR_IDS, pos, (8, 7))
    compensating = _first_at((*EXTRA_COLOR_IDS, BORDER_COLOR_ID), pos, (1, 2))
    link_key = f"{frustrated}.{compensating}"
    linked = frustrated is not None and compensating is not None and link_key in texts["link"]

    notes: list[PsychoEmotionalHighlight] = []
    if linked:
        notes.append(
            PsychoEmotionalHighlight(key=f"link.{link_key}", text=texts["link"][link_key], position_depth=3)
        )

    for color_id in BASIC_COLOR_IDS:
        if pos[color_id] < 6 or (linked and color_id == frustrated):
            continue
        key = f"{color_id}.{pos[color_id]}"
        notes.append(
            PsychoEmotionalHighlight(
                key=f"anxiety.{key}", text=texts["anxiety"][key], position_depth=pos[color_id] - 5
            )
        )

    for color_id in EXTRA_COLOR_IDS:
        if pos[color_id] > 3 or (linked and color_id == compensating):
            continue
        key = f"{color_id}.{pos[color_id]}"
        notes.append(
            PsychoEmotionalHighlight(
                key=f"comp.{key}", text=texts["comp"][key], position_depth=4 - pos[color_id]
            )
        )

    violet = pos[BORDER_COLOR_ID]
    if violet <= 3 and not (linked and compensating == BORDER_COLOR_ID):
        notes.append(
            PsychoEmotionalHighlight(
                key="comp.5.forward", text=texts["comp"]["5.forward"], position_depth=4 - violet
            )
        )

    return sorted(notes, key=lambda note: -note.position_depth)  # stable: равные — в порядке блоков


def _note_text(sign: str, colors: list[int], texts: dict) -> str:
    if sign == "plus_minus":
        return texts["pm"]["".join(map(str, colors))]
    if len(colors) == 1:
        return texts["single"][sign][str(colors[0])]
    return texts["pair"][sign]["".join(map(str, sorted(colors)))]


def _positions(
    list1: list[int], list2: list[int], texts: dict
) -> list[PsychoEmotionalPositionNote]:
    """Все соседние сочетания функциональных зон и связи ``+−``.

    Количество абзацев зависит от реального рисунка выбора, а не всегда равно
    четырём парам: длинная зона читается последовательностью соседних пар,
    одиночная — отдельным цветом.
    """
    return [
        PsychoEmotionalPositionNote(
            sign=group["sign"],
            colors=group["colors"],
            text=_note_text(group["sign"], group["colors"], texts),
        )
        for group in functional_combinations(list1, list2)
    ]


def _mcv_groups(list1: list[int], list2: list[int], texts: dict) -> list[PsychoEmotionalMcvGroup]:
    """Отдельный слой МЦВ — типологический смысл тех же сочетаний.

    Чтобы не дублировать дословно ситуационную трактовку, пара раскрывается
    через вклад каждой ведущей тенденции в её функциональной зоне.
    """
    notes: list[PsychoEmotionalMcvGroup] = []
    for group in functional_combinations(
        list1, list2, all_rejection_pairs=True
    ):
        sign = group["sign"]
        colors = group["colors"]
        if sign == "plus_minus":
            text = " ".join(
                (
                    texts["single"][SIGN_PLUS][str(colors[0])],
                    texts["single"][SIGN_MINUS][str(colors[1])],
                )
            )
        else:
            text = " ".join(texts["single"][sign][str(color)] for color in colors)
        notes.append(
            PsychoEmotionalMcvGroup(
                sign=sign,
                colors=colors,
                stable=group["stable"],
                text=text,
            )
        )
    return notes


def interpret(metrics: dict, list1: list[int], list2: list[int]) -> PsychoEmotionalInterpretation:
    """Метрики прохождения → гипотезы на языке запроса.

    Качество прохождения (флаг достоверности и причины) здесь не озвучивается:
    карточка специалиста уже показывает его бейджем, повтор в толковании —
    лишний текст.
    """
    texts = tr("psychoemotional_interpretation")
    pos = {color_id: rank for rank, color_id in enumerate(list2, start=1)}

    reading = []
    if metrics["split"]["instability"]:
        reading.append(texts["reading"]["split"])
    if metrics["d"]["situationally_unstable"]:
        reading.append(texts["reading"]["d_high"])

    indices = [
        PsychoEmotionalIndexNote(metric=metric, level=level, text=texts["level"][metric][level])
        for metric, level in (
            ("anxiety", metrics["anxiety"]["level"]),
            ("so", metrics["so"]["level"]),
            ("vk", metrics["vk"]["level"]),
        )
    ]

    return PsychoEmotionalInterpretation(
        reading=reading,
        highlights=_highlights(pos, texts),
        indices=indices,
        positions=_positions(list1, list2, texts),
        mcv_groups=_mcv_groups(list1, list2, texts),
    )
